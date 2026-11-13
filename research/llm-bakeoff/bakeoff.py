"""P1-09 LLM bake-off harness (ADR-003). Run from the repo root:

    uv run python research/llm-bakeoff/bakeoff.py fetch          # sources + feed items (free)
    uv run python research/llm-bakeoff/bakeoff.py run T5 --models claude-haiku-5-5 ...
    uv run python research/llm-bakeoff/bakeoff.py run T1 --models qwen2.5:7b ...
    uv run python research/llm-bakeoff/score.py                  # tables + rating sheets

Tasks (prompts in brief/llm/prompts/, versioned):
  T5 claim extraction (claims.v1)   one call per story per model, on the full source text
  T6 script (script.v1)             two 5-story editions, from the same rule-checked claims
  T7 critic (critic.v1)             each edition's Sonnet script, clean and with planted errors
  T1 tagging (tag.v1)               ~120 real feed items
  T2 same-event (same_event.v1)     40 item pairs

Every paid call goes through brief.llm.client.AnthropicJSON: budget check first
(preparation cap $7, daily cap $1.50), actual cost in finance/usage-ledger.jsonl.
Outputs are written to research/llm-bakeoff/runs/<task>/<model>/<id>.json; an existing
output is never requested again, so a run blocked by the daily cap resumes the next day
without paying twice. Source texts and feed items stay in cache/llm-bakeoff/ (git-ignored).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import random
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from brief.budget import Budget, BudgetExceededError, load_config  # noqa: E402
from brief.llm.client import AnthropicJSON, LLMError, OllamaJSON, load_models  # noqa: E402
from brief.net import FetchPolicy, fetch  # noqa: E402
from brief.site.deploy import read_dotenv  # noqa: E402

CACHE = ROOT / "cache" / "llm-bakeoff"
RUNS = HERE / "runs"
PROMPTS = ROOT / "brief" / "llm" / "prompts"
PROMPT_FILES = {
    "T5": "claims.v2",
    "T6": "script.v2",  # v1 runs kept in runs/T6-script.v1
    "T7": "critic.v1",
    "T1": "tag.v1",
    "T2": "same_event.v1",
}
POLICY = FetchPolicy(
    max_bytes=2_000_000, timeout_s=20.0, user_agent="AIDailyBrief/0.1 (research; LLM bake-off)"
)
FEEDS = {
    "arxiv-cs-cl": "https://rss.arxiv.org/rss/cs.CL",
    "huggingface-blog": "https://huggingface.co/blog/feed.xml",
    "ollama-releases": "https://github.com/ollama/ollama/releases.atom",
    "hn-frontpage": "https://hnrss.org/frontpage",
    "verge": "https://www.theverge.com/rss/index.xml",
    "google-ai-blog": "https://blog.google/technology/ai/rss/",
}
ITEMS_PER_FEED = 20
CATEGORIES = ["model_release", "research", "open_source", "business", "policy"]
CLAIM_TYPES = [
    "fact",
    "vendor_claim",
    "benchmark_vendor",
    "benchmark_independent",
    "availability",
    "interpretation",
    "forecast",
    "quote",
]
EDITIONS = {
    "E1": ["s01-ripple", "s03-retrace", "s05-lerobot", "s07-nvidia", "s09-fractile"],
    "E2": ["s02-fable52", "s04-rtl", "s06-pytorch", "s08-gsa", "s10-nist"],
}
REFERENCE = "claude-sonnet-5-5@high"  # T5 claims fed to T6/T7; T6 script checked in T7
CRITIC_BASE_MODEL = REFERENCE
CRITIC_SCRIPTS = "T6-script.v1"  # T7 inputs stay fixed: Sonnet's v1 scripts
LOCAL_TIMEOUT_S = 15.0  # ADR-003 fallback rule


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


def _str() -> dict[str, Any]:
    return {"type": "string"}


SCHEMAS: dict[str, dict[str, Any]] = {
    "T5": _obj(
        {
            "claims": {
                "type": "array",
                "items": _obj(
                    {
                        "claim_text": _str(),
                        "claim_type": {"type": "string", "enum": CLAIM_TYPES},
                        "materiality": {"type": "string", "enum": ["material", "minor"]},
                        "evidence_url": _str(),
                        "excerpt": _str(),
                    }
                ),
            }
        }
    ),
    "T6": _obj(
        {
            "hook": _str(),
            "outro": _str(),
            "stories": {
                "type": "array",
                "items": _obj(
                    {
                        "rank": {"type": "integer"},
                        "story_id": _str(),
                        "headline": _str(),
                        "summary": _str(),
                        "why_it_matters": _str(),
                        "limitations": _str(),
                        "card_text": _str(),
                        "narration": _str(),
                    }
                ),
            },
        }
    ),
    "T7": _obj(
        {
            "problems": {
                "type": "array",
                "items": _obj(
                    {
                        "rank": {"type": "integer"},
                        "quote": _str(),
                        "type": {
                            "type": "string",
                            "enum": [
                                "number",
                                "name",
                                "date",
                                "attribution",
                                "overclaim",
                                "unsupported",
                            ],
                        },
                        "explanation": _str(),
                    }
                ),
            }
        }
    ),
    "T1": _obj(
        {
            "in_scope": {"type": "boolean"},
            "category": {"type": "string", "enum": [*CATEGORIES, "none"]},
            "entities": {"type": "array", "items": _str()},
        }
    ),
    "T2": _obj({"same_event": {"type": "boolean"}, "reason": _str()}),
}
MAX_TOKENS = {"T5": 10000, "T6": 10000, "T7": 6000, "T1": 1500, "T2": 1000}
EFFORT = {"T5": "medium", "T6": "medium", "T7": "medium", "T1": "low", "T2": "low"}


# ------------------------------------------------------------------ text extraction


class _Text(HTMLParser):
    SKIP = frozenset(
        [
            "script",
            "style",
            "noscript",
            "nav",
            "header",
            "footer",
            "aside",
            "form",
            "svg",
            "button",
            "template",
            "iframe",
        ]
    )
    BLOCK = frozenset(
        [
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "li",
            "tr",
            "blockquote",
            "pre",
            "div",
            "section",
            "article",
            "td",
            "th",
            "br",
            "dd",
            "dt",
            "figcaption",
        ]
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in "".join(p.parts).splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


LOOSE = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
    }
)


def loose(text: str) -> str:
    """Whitespace, quote and dash differences ignored (copying from HTML changes them)."""
    return normalise(text.translate(LOOSE)).lower()


# ------------------------------------------------------------------ data


def _config() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((HERE / "stories.yaml").read_text(encoding="utf-8"))
    return data


def stories() -> list[dict[str, Any]]:
    return list(_config()["stories"])


def edition_date() -> str:
    return str(_config()["edition_date"])


def _story(sid: str) -> dict[str, Any]:
    return next(s for s in stories() if s["id"] == sid)


def source_text(story_id: str) -> str:
    return (CACHE / "sources" / f"{story_id}.txt").read_text(encoding="utf-8")


def items() -> list[dict[str, str]]:
    return list(json.loads((CACHE / "items.json").read_text(encoding="utf-8")))


def pairs() -> list[dict[str, str]]:
    """40 item pairs: the 30 most similar titles across different feeds, plus 10 random."""
    its = items()

    def toks(s: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9][a-z0-9.\-]+", s.lower()) if len(w) > 2}

    scored = []
    for a, b in itertools.combinations(its, 2):
        if a["feed"] == b["feed"]:
            continue
        ta, tb = toks(a["title"]), toks(b["title"])
        if ta and tb:
            scored.append((len(ta & tb) / len(ta | tb), a["id"], b["id"]))
    scored.sort(reverse=True)
    chosen = [(x[1], x[2]) for x in scored[:30]]
    rest = [(x[1], x[2]) for x in scored[30:]]
    chosen += random.Random(20261113).sample(  # noqa: S311 - seeded sample, not security
        rest, min(10, len(rest))
    )
    return [{"id": f"p{n:02d}", "a": a, "b": b} for n, (a, b) in enumerate(chosen, 1)]


def verified_claims(story_id: str, model: str = REFERENCE) -> list[dict[str, Any]]:
    """Claims from one model's T5 output that pass both rules (URL and verbatim excerpt).

    A stand-in for editor verification, so every T6/T7 model gets identical input.
    """
    out = RUNS / "T5" / model / f"{story_id}.json"
    if not out.exists():
        raise SystemExit(f"T6/T7 need {model}'s T5 output for {story_id}; run T5 first")
    rec = json.loads(out.read_text(encoding="utf-8"))
    story = _story(story_id)
    text = loose(source_text(story_id))
    return [
        c
        for c in (rec.get("data") or {}).get("claims", [])
        if c["evidence_url"] == story["url"] and loose(c["excerpt"]) in text
    ]


# ------------------------------------------------------------------ fetch


def parse_feed(body: bytes) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(body)  # noqa: S314 - stdlib expat limits entity expansion
    except ET.ParseError:
        return []
    atom = "{http://www.w3.org/2005/Atom}"
    out = []
    for node in root.iter():
        if node.tag == "item":
            title, desc = node.findtext("title") or "", node.findtext("description") or ""
        elif node.tag == f"{atom}entry":
            title = node.findtext(f"{atom}title") or ""
            desc = node.findtext(f"{atom}summary") or node.findtext(f"{atom}content") or ""
        else:
            continue
        if title.strip():
            out.append(
                {"title": normalise(title), "description": normalise(html_to_text(desc))[:600]}
            )
    return out


def cmd_fetch() -> int:
    (CACHE / "sources").mkdir(parents=True, exist_ok=True)
    manifest = []
    for s in stories():
        r = fetch(s["url"], POLICY)
        ok = r.status == 200 and not r.truncated and bool(r.body)
        text = html_to_text(r.body.decode("utf-8", "replace")) if ok else ""
        if ok:
            (CACHE / "sources" / f"{s['id']}.txt").write_text(text, encoding="utf-8")
        manifest.append(
            {
                "id": s["id"],
                "url": s["url"],
                "final_url": r.final_url,
                "status": r.status,
                "error": r.error,
                "truncated": r.truncated,
                "words": len(text.split()),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )
        print(f"{s['id']:14} {r.status} {len(text.split()):6} words {r.error or ''}")
    (HERE / "sources-manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    collected: list[dict[str, str]] = []
    for feed, url in FEEDS.items():
        r = fetch(url, POLICY)
        got = parse_feed(r.body) if r.status == 200 else []
        print(f"feed {feed:18} {r.status} {len(got)} items {r.error or ''}")
        for it in got[:ITEMS_PER_FEED]:
            collected.append({"id": f"i{len(collected) + 1:03d}", "feed": feed, **it})
    (CACHE / "items.json").write_text(json.dumps(collected, indent=1, ensure_ascii=False))
    print(f"{len(collected)} feed items")
    return 0


# ------------------------------------------------------------------ task inputs


def script_input(eid: str) -> str:
    parts = [f'<stories edition_date="{edition_date()}">']
    for rank, sid in enumerate(EDITIONS[eid], 1):
        s = _story(sid)
        claims = "\n".join(
            f"  - [{c['claim_type']}] {c['claim_text']}" for c in verified_claims(sid)
        )
        parts.append(
            f'<story rank="{rank}" story_id="{sid}" category="{s["category"]}" '
            f'publisher="{s["publisher"]}" published="{s["published"]}">\n'
            f"Source title: {s['title']}\nVerified claims:\n{claims}\n</story>"
        )
    parts.append("</stories>")
    return "\n".join(parts)


def script_text(script: dict[str, Any]) -> str:
    lines = [f"Hook: {script['hook']}"]
    for st in sorted(script["stories"], key=lambda x: x["rank"]):
        lines += [
            f"\nStory {st['rank']}",
            f"Headline: {st['headline']}",
            f"Card: {st['card_text']}",
            f"Narration: {st['narration']}",
            f"Summary: {st['summary']}",
            f"Why it matters: {st['why_it_matters']}",
        ]
    lines.append(f"\nOutro: {script['outro']}")
    return "\n".join(lines)


def critic_input(eid: str, script: dict[str, Any]) -> str:
    claims = []
    for rank, sid in enumerate(EDITIONS[eid], 1):
        s = _story(sid)
        claims.append(
            f'<story rank="{rank}" publisher="{s["publisher"]}" published="{s["published"]}">'
        )
        claims += [f"- [{c['claim_type']}] {c['claim_text']}" for c in verified_claims(sid)]
        claims.append("</story>")
    return (
        f'<claims edition_date="{edition_date()}">\n'
        + "\n".join(claims)
        + f"\n</claims>\n<script>\n{script_text(script)}\n</script>"
    )


def plant_errors(script: dict[str, Any], eid: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Deterministically plant up to 5 checkable errors in a copy of a clean script."""
    s = json.loads(json.dumps(script))
    by_rank = {st["rank"]: st for st in s["stories"]}
    planted: list[dict[str, Any]] = []
    pubs = [_story(sid)["publisher"] for sid in EDITIONS[eid]]

    def number_change(st: dict[str, Any], rank: int) -> None:
        m = re.search(r"\d+(?:[.,]\d+)?", st["narration"])
        if m:
            old = m.group(0)
            new = old + "5" if "." in old else str(int(old.replace(",", "")) * 2)
            st["narration"] = st["narration"].replace(old, new, 1)
            planted.append({"rank": rank, "type": "number", "text": new})

    def name_swap(st: dict[str, Any], rank: int) -> None:
        own = pubs[rank - 1]
        other = next(p for p in pubs if p != own)
        if own in st["narration"]:
            st["narration"] = st["narration"].replace(own, other, 1)
            planted.append({"rank": rank, "type": "name", "text": other})

    def overclaim(st: dict[str, Any], rank: int) -> None:
        add = "It is the most capable system of its kind ever released."
        st["narration"] = st["narration"].rstrip() + " " + add
        planted.append({"rank": rank, "type": "overclaim", "text": add})

    def date_word(st: dict[str, Any], rank: int) -> None:
        st["narration"] = "Today, " + st["narration"][0].lower() + st["narration"][1:]
        planted.append({"rank": rank, "type": "date", "text": "Today,"})

    def unsupported(st: dict[str, Any], rank: int) -> None:
        add = "It will be free for everyone until the end of 2027."
        st["summary"] = st["summary"].rstrip() + " " + add
        planted.append({"rank": rank, "type": "unsupported", "text": add})

    for fn, rank in (
        (number_change, 1),
        (name_swap, 2),
        (overclaim, 3),
        (date_word, 4),
        (unsupported, 5),
    ):
        if rank in by_rank:
            fn(by_rank[rank], rank)
    return s, planted


def jobs(task: str) -> list[tuple[str, str]]:
    """(job id, user message) for a task."""
    if task == "T5":
        return [
            (
                s["id"],
                f'<source url="{s["url"]}" publisher="{s["publisher"]}" '
                f'published="{s["published"]}">\n{source_text(s["id"])}\n</source>',
            )
            for s in stories()
        ]
    if task == "T6":
        return [(eid, script_input(eid)) for eid in EDITIONS]
    if task == "T7":
        out = []
        for eid in EDITIONS:
            base = json.loads(
                (RUNS / CRITIC_SCRIPTS / CRITIC_BASE_MODEL / f"{eid}.json").read_text()
            )
            mutated, _planted = plant_errors(base["data"], eid)
            out.append((f"{eid}-clean", critic_input(eid, base["data"])))
            out.append((f"{eid}-planted", critic_input(eid, mutated)))
        return out
    if task == "T1":
        return [
            (it["id"], f"<item>\nTitle: {it['title']}\nDescription: {it['description']}\n</item>")
            for it in items()
        ]
    if task == "T2":
        by_id = {it["id"]: it for it in items()}
        return [
            (
                p["id"],
                "".join(
                    f"<item_{k}>\nTitle: {by_id[p[k]]['title']}\n"
                    f"Description: {by_id[p[k]]['description']}\n</item_{k}>\n"
                    for k in ("a", "b")
                ),
            )
            for p in pairs()
        ]
    raise SystemExit(f"unknown task {task}")


def validator(task: str, job: str) -> Any:
    def check(d: dict[str, Any]) -> None:
        if task == "T6":
            got = sorted(st["rank"] for st in d["stories"])
            if got != list(range(1, len(EDITIONS[job]) + 1)):
                raise ValueError(f"ranks {got}, expected 1..{len(EDITIONS[job])}")
        if task == "T5" and len(d["claims"]) > 15:
            raise ValueError(f"{len(d['claims'])} claims (asked for at most 10)")

    return check


# ------------------------------------------------------------------ run


def memory_snapshot() -> dict[str, str]:
    def out(args: list[str]) -> str:
        return subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()  # noqa: S603

    return {"swap": out(["sysctl", "-n", "vm.swapusage"]), "ollama_ps": out(["ollama", "ps"])}


def cmd_run(task: str, model_names: list[str], limit: int, effort: str | None = None) -> int:
    todo = jobs(task)[: limit or None]
    models = load_models(ROOT / "config" / "llm_routes.yaml")
    env = read_dotenv(ROOT / ".env")
    if env.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = env["ANTHROPIC_API_KEY"]
    budget = Budget(
        load_config(ROOT / "config" / "budget_periods.yaml"),
        usage_path=ROOT / "finance" / "usage-ledger.jsonl",
        cash_path=ROOT / "finance" / "cash-ledger.csv",
    )
    hosted = AnthropicJSON(budget, models)
    local = OllamaJSON(timeout_s=LOCAL_TIMEOUT_S, keep_alive="10m")
    # gemma4:e4b runs on Ollama's MLX runner, which reports "structured output is
    # unavailable": the schema goes in the prompt and the reply is validated by us.
    unstructured = OllamaJSON(
        timeout_s=LOCAL_TIMEOUT_S, keep_alive="10m", structured=False, think=False
    )
    system = (PROMPTS / f"{PROMPT_FILES[task]}.md").read_text(encoding="utf-8")
    for model in model_names:
        info = models.get(model)
        if info is None:
            raise SystemExit(f"{model} is not in config/llm_routes.yaml")
        variant = f"{model}@{effort}" if effort else model  # e.g. claude-sonnet-5-5@high
        out_dir = RUNS / task / variant
        out_dir.mkdir(parents=True, exist_ok=True)
        meta: dict[str, Any] = {"model": model, "task": task, "started": time.time()}
        if info.provider == "ollama":
            meta["memory_before"] = memory_snapshot()
        done = skipped = 0
        for job, user in todo:
            path = out_dir / f"{job}.json"
            if path.exists():
                skipped += 1
                continue
            rec: dict[str, Any] = {
                "task": task,
                "model": model,
                "effort": effort or EFFORT[task],
                "job": job,
                "prompt": PROMPT_FILES[task],
            }
            try:
                if info.provider == "anthropic":
                    r = hosted.complete(
                        model,
                        system,
                        user,
                        SCHEMAS[task],
                        f"bakeoff:{task}:{job}",
                        max_tokens=MAX_TOKENS[task],
                        effort=effort or EFFORT[task],
                        validate=validator(task, job),
                    )
                else:
                    client = unstructured if model.startswith("gemma4") else local
                    r = client.complete(
                        model, system, user, SCHEMAS[task], validate=validator(task, job)
                    )
                rec.update(
                    data=r.data,
                    input_tokens=r.input_tokens,
                    output_tokens=r.output_tokens,
                    cost_usd=r.cost_usd,
                    latency_s=round(r.latency_s, 3),
                    request_id=r.request_id,
                    stop_reason=r.stop_reason,
                    extra=r.extra,
                    error=None,
                )
            except BudgetExceededError as exc:
                print(f"\nstopped by the budget: {exc}\nrerun later; finished outputs are kept")
                return 2
            except LLMError as exc:  # invalid, refused, truncated or timed out: kept and counted
                rec.update(data=None, error=f"{type(exc).__name__}: {exc}")
            path.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
            done += 1
            status = "ERR " + rec["error"][:70] if rec["error"] else f"{rec['latency_s']:.1f}s"
            print(f"{task} {variant:24} {job:16} {status}", flush=True)
        if info.provider == "ollama" and done:
            meta["memory_loaded"] = memory_snapshot()
            local.unload(model)
            time.sleep(2)
            meta["unloaded"] = not any(m.get("name") == model for m in local.loaded())
            meta["memory_after_unload"] = memory_snapshot()
        meta.update(finished=time.time(), done=done, skipped=skipped)
        (out_dir / f"_run-{int(meta['started'])}.json").write_text(json.dumps(meta, indent=1))
        print(f"{task} {variant}: {done} new, {skipped} already done")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="P1-09 LLM bake-off")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    r = sub.add_parser("run")
    r.add_argument("task", choices=list(PROMPT_FILES))
    r.add_argument("--models", nargs="+", required=True)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--effort", choices=["low", "medium", "high"], default=None)
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        return cmd_fetch()
    return cmd_run(args.task, args.models, args.limit, args.effort)


if __name__ == "__main__":
    raise SystemExit(main())
