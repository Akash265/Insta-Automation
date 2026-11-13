"""Score the P1-09 bake-off runs (no API calls). Run from the repo root:

    uv run python research/llm-bakeoff/score.py

Writes research/llm-bakeoff/results/summary.md and scores.json, and blind rating sheets
in research/llm-bakeoff/ratings/ (models shown as letters; the key is a separate file,
not to be opened until the sheets are scored).

Rule scores (automatic):
  T5  url_ok: evidence_url is exactly the given source URL (models must never invent URLs)
      excerpt_exact: the excerpt appears in the source text (whitespace normalised)
      excerpt_loose: the same, ignoring case, quote and dash styles
  T6  the edition checks C04/C06/C07/C09 from `brief validate`, plus length limits
  T7  planted errors found (right story, quote overlapping the planted text); flags on the
      clean script are listed for the editor (each is either a real issue or a false alarm)
  T1  agreement with Haiku on in_scope and category; latency; failures and invalid output
  T2  agreement with Haiku on same_event
Editor scores (claim precision, claim-type accuracy, script quality) come from the sheets.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import bakeoff as b  # noqa: E402

from brief.edition.checks import validate_edition  # noqa: E402
from brief.edition.schema import (  # noqa: E402
    Claim,
    Edition,
    EventAtBasis,
    Evidence,
    Script,
    SourceType,
    Story,
)

OUT = HERE / "results"
SHEETS = HERE / "ratings"
# Model variants: "<model>@<effort>" folders are runs at a non-default effort.
HOSTED = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-sonnet-5-5@high", "claude-opus-5-5"]
SHEET_MODELS = {"claude-haiku-5-5", "claude-sonnet-5-5@high", "claude-opus-5-5"}  # editor rates
LOCAL = ["qwen2.5:7b", "gemma4:e4b"]
RNG_SEED = 20261113
ASSUMED_REPAIR_RATE = 0.20  # ADR-003 assumption (repairs ~20% of T5-T7)


def runs(task: str, model: str) -> dict[str, dict[str, Any]]:
    folder = b.RUNS / task / model
    if not folder.exists():
        return {}
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(folder.glob("*.json"))
        if not p.name.startswith("_")
    }


def run_meta(task: str, model: str) -> dict[str, Any]:
    metas = sorted((b.RUNS / task / model).glob("_run-*.json"))
    return json.loads(metas[-1].read_text()) if metas else {}


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


def usage(recs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in recs.values() if r.get("input_tokens") is not None]
    if not ok:
        return {}
    lat = sorted(r["latency_s"] for r in ok)
    return {
        "calls": len(recs),
        "failed": sum(1 for r in recs.values() if r.get("error")),
        "mean_in": statistics.mean(r["input_tokens"] for r in ok),
        "mean_out": statistics.mean(r["output_tokens"] for r in ok),
        "cost": sum(r.get("cost_usd") or 0 for r in ok),
        "p50_s": statistics.median(lat),
        "p95_s": lat[max(0, round(0.95 * len(lat)) - 1)],
        "max_s": lat[-1],
        "total_s": sum(lat),
    }


# ------------------------------------------------------------------ T5


def score_t5() -> tuple[dict[str, Any], list[list[str]]]:
    res: dict[str, Any] = {}
    sheet: list[dict[str, Any]] = []
    for model in HOSTED:
        recs = runs("T5", model)
        if not recs:
            continue
        n = url_ok = exact = loose_ok = short = material = 0
        types: dict[str, int] = {}
        for sid, rec in recs.items():
            story = b._story(sid)
            text = b.source_text(sid)
            for c in (rec.get("data") or {}).get("claims", []):
                n += 1
                u = c["evidence_url"] == story["url"]
                e = b.normalise(c["excerpt"]) in b.normalise(text)
                lo = b.loose(c["excerpt"]) in b.loose(text)
                url_ok, exact, loose_ok = url_ok + u, exact + e, loose_ok + lo
                short += len(c["excerpt"]) <= 300
                material += c["materiality"] == "material"
                types[c["claim_type"]] = types.get(c["claim_type"], 0) + 1
                if model in SHEET_MODELS:
                    sheet.append({"story": sid, "model": model, **c, "url_ok": u, "excerpt_ok": lo})
        res[model] = {
            "stories": len(recs),
            "claims": n,
            "claims_per_story": n / max(1, len(recs)),
            "url_ok": pct(url_ok, n),
            "excerpt_exact": pct(exact, n),
            "excerpt_loose": pct(loose_ok, n),
            "excerpt_le_300": pct(short, n),
            "material": pct(material, n),
            "types": types,
            "usage": usage(recs),
        }
    return res, blind_sheet(sheet, "T5")


def blind_sheet(rows: list[dict[str, Any]], task: str) -> list[list[str]]:
    """Per story, shuffle models into letters; write the key separately."""
    rng = random.Random(f"{RNG_SEED}-{task}")  # noqa: S311 - blinding, not security
    key: dict[str, dict[str, str]] = {}
    out = [["row", "story", "label", "claim_text", "claim_type", "materiality", "excerpt",
            "rule_url_ok", "rule_excerpt_ok", "editor_supported_y_n", "editor_type_correct_y_n",
            "editor_would_use_y_n", "notes"]]  # fmt: skip
    for sid in sorted({r["story"] for r in rows}):
        models = sorted({r["model"] for r in rows if r["story"] == sid})
        rng.shuffle(models)
        key[sid] = {chr(65 + i): m for i, m in enumerate(models)}
        label = {m: lab for lab, m in key[sid].items()}
        for r in sorted((r for r in rows if r["story"] == sid), key=lambda r: label[r["model"]]):
            out.append([str(len(out)), sid, label[r["model"]], r["claim_text"], r["claim_type"],
                        r["materiality"], r["excerpt"], "y" if r["url_ok"] else "n",
                        "y" if r["excerpt_ok"] else "n", "", "", "", ""])  # fmt: skip
    SHEETS.mkdir(exist_ok=True)
    (SHEETS / f"KEY-{task}-do-not-open-until-rated.json").write_text(json.dumps(key, indent=1))
    return out


# ------------------------------------------------------------------ T6


def edition_from(eid: str, script: dict[str, Any]) -> Edition:
    day = b.edition_date()
    manifest = {m["id"]: m for m in json.loads((HERE / "sources-manifest.json").read_text())}
    stories = []
    for st in sorted(script["stories"], key=lambda x: x["rank"]):
        sid = b.EDITIONS[eid][st["rank"] - 1]
        src = b._story(sid)
        published = datetime.fromisoformat(f"{src['published']}T09:00:00+00:00")
        fetched = datetime.fromisoformat(manifest[sid]["fetched_at"])
        claims = [
            Claim(claim_text=c["claim_text"], claim_type=c["claim_type"],
                  materiality=c["materiality"], status="supported", confidence="high",
                  evidence=[Evidence(url=src["url"], publisher=src["publisher"], source_tier=1,
                                     stance="supports", excerpt=c["excerpt"][:300],
                                     retrieved_at=fetched)],
                  verified_by="bake-off rules", verified_at=fetched)
            for c in b.verified_claims(sid)
        ]  # fmt: skip
        stories.append(
            Story(
                story_id=sid,
                rank=st["rank"],
                category=src["category"],
                headline=st["headline"],
                summary=st["summary"],
                why_it_matters=st["why_it_matters"],
                limitations=st["limitations"] or None,
                publisher=src["publisher"],
                source_type=SourceType.HTML_PAGE,
                source_tier=1,
                primary_source_url=src["url"],
                published_at=published,
                event_at=published,
                event_at_basis=EventAtBasis.SAME_AS_PUBLISHED,
                collected_at=fetched,
                selected_reason="bake-off",
                claims=claims,
                card_text=st["card_text"],
                narration=st["narration"],
            )
        )
    return Edition(
        issue_key=f"ADB-{day}",
        issue_date=day,
        cutoff_at=f"{day}T11:30:00+00:00",
        stories=stories,
        script=Script(version=1, hook=script["hook"], outro=script["outro"]),
    )


def score_t6() -> tuple[dict[str, Any], list[list[str]]]:
    res: dict[str, Any] = {}
    rows: list[tuple[str, str, str]] = []
    for model in HOSTED:
        recs = runs("T6", model)
        if not recs:
            continue
        per: dict[str, Any] = {}
        for eid, rec in recs.items():
            s = rec.get("data")
            if not s:
                per[eid] = {"error": rec.get("error")}
                continue
            report = validate_edition(edition_from(eid, s), "draft")
            issues = [f"{i.code} {i.severity}: {i.message} (story {i.story_rank})"
                      for i in report.issues if i.code in ("C04", "C06", "C07", "C09")]  # fmt: skip
            sts = s["stories"]
            words = (
                len(s["hook"].split())
                + len(s["outro"].split())
                + sum(len(x["narration"].split()) for x in sts)
            )
            limits = []
            for x in sts:
                nw = len(x["narration"].split())
                if not 25 <= nw <= 40:
                    limits.append(f"story {x['rank']} narration {nw} words (25-40)")
                if len(x["headline"]) > 90:
                    limits.append(f"story {x['rank']} headline {len(x['headline'])} chars")
                if len(x["card_text"]) > 90:
                    limits.append(f"story {x['rank']} card {len(x['card_text'])} chars")
            per[eid] = {"narration_words": words, "check_issues": issues, "limit_issues": limits}
            rows.append((eid, model, b.script_text(s)))
        res[model] = {"editions": per, "usage": usage(recs)}
    rng = random.Random(f"{RNG_SEED}-T6")  # noqa: S311 - blinding, not security
    key: dict[str, dict[str, str]] = {}
    sheet = [["edition", "label", "script", "editor_accuracy_1_5", "editor_clarity_1_5",
              "editor_would_publish_y_n", "notes"]]  # fmt: skip
    for eid in sorted({r[0] for r in rows}):
        models = sorted(m for e, m, _ in rows if e == eid)
        rng.shuffle(models)
        key[eid] = {chr(65 + i): m for i, m in enumerate(models)}
        for lab, m in key[eid].items():
            sheet.append([eid, lab, next(t for e, mm, t in rows if e == eid and mm == m),
                          "", "", "", ""])  # fmt: skip
    SHEETS.mkdir(exist_ok=True)
    (SHEETS / "KEY-T6-do-not-open-until-rated.json").write_text(json.dumps(key, indent=1))
    return res, sheet


# ------------------------------------------------------------------ T7


def score_t7() -> tuple[dict[str, Any], list[list[str]]]:
    res: dict[str, Any] = {}
    review = [["model", "edition", "rank", "type", "quote", "explanation",
               "editor_real_issue_y_n"]]  # fmt: skip
    for model in HOSTED:
        recs = runs("T7", model)
        if not recs:
            continue
        found = total = clean_flags = 0
        missed: list[str] = []
        for eid in b.EDITIONS:
            base_path = b.RUNS / "T6" / b.CRITIC_BASE_MODEL / f"{eid}.json"
            if not base_path.exists():
                continue
            _, planted = b.plant_errors(json.loads(base_path.read_text())["data"], eid)
            got = (recs.get(f"{eid}-planted", {}).get("data") or {}).get("problems", [])
            for p in planted:
                total += 1
                hit = any(
                    q["rank"] == p["rank"]
                    and (
                        b.loose(p["text"]) in b.loose(q["quote"])
                        or b.loose(q["quote"]) in b.loose(p["text"])
                    )
                    for q in got
                )
                found += hit
                if not hit:
                    missed.append(f"{eid} story {p['rank']} {p['type']}")
            clean = (recs.get(f"{eid}-clean", {}).get("data") or {}).get("problems", [])
            clean_flags += len(clean)
            review += [[model, eid, str(q["rank"]), q["type"], q["quote"], q["explanation"], ""]
                       for q in clean]  # fmt: skip
        res[model] = {"planted_found": pct(found, total), "missed": missed,
                      "flags_on_clean_scripts": clean_flags, "usage": usage(recs)}  # fmt: skip
    return res, review


# ------------------------------------------------------------------ T1 / T2


def score_local(task: str, fields: list[str]) -> dict[str, Any]:
    ref = runs(task, "claude-haiku-5-5")
    res: dict[str, Any] = {"claude-haiku-5-5": {"usage": usage(ref)}}
    for model in LOCAL:
        recs = runs(task, model)
        if not recs:
            continue
        agree = {f: 0 for f in fields}
        both = 0
        for job, rec in recs.items():
            r0 = (ref.get(job) or {}).get("data")
            r1 = rec.get("data")
            if r0 and r1:
                both += 1
                for f in fields:
                    agree[f] += r0[f] == r1[f]
        meta = run_meta(task, model)
        first = min(recs.values(), key=lambda r: r.get("job", ""))
        res[model] = {
            "agreement_with_haiku": {f: pct(agree[f], both) for f in fields},
            "usage": usage(recs),
            "failures_and_invalid": pct(sum(1 for r in recs.values() if r.get("error")), len(recs)),
            "first_call_load_s": (first.get("extra") or {}).get("load_s"),
            "unloaded_after": meta.get("unloaded"),
            "memory_loaded": (meta.get("memory_loaded") or {}).get("ollama_ps"),
            "swap_before_after": [
                (meta.get("memory_before") or {}).get("swap"),
                (meta.get("memory_loaded") or {}).get("swap"),
            ],
        }
    return res


# ------------------------------------------------------------------ report


def per_edition_cost(scores: dict[str, Any], model: str) -> dict[str, Any]:
    """Measured mean cost per call x calls per edition (ADR-003 volumes) for one model."""

    def mean_cost(task: str) -> float | None:
        u = (scores[task].get(model) or {}).get("usage") or {}
        return u["cost"] / u["calls"] if u.get("calls") else None

    t5, t6, t7 = mean_cost("T5"), mean_cost("T6"), mean_cost("T7")
    if t5 is None or t6 is None or t7 is None:
        return {}
    core = 10 * t5 + t6 + t7  # ADR-003: ~10 claim extractions (stories + alternates)
    return {"T5_per_story": t5, "T6": t6, "T7": t7, "core": core,
            "with_assumed_repairs": core * (1 + ASSUMED_REPAIR_RATE),
            "month_22_editions": core * (1 + ASSUMED_REPAIR_RATE) * 22}  # fmt: skip


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    SHEETS.mkdir(exist_ok=True)
    t5, t5_sheet = score_t5()
    t6, t6_sheet = score_t6() if (b.RUNS / "T6").exists() else ({}, [])
    t7, t7_sheet = score_t7() if (b.RUNS / "T7").exists() else ({}, [])
    scores = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "T5": t5, "T6": t6, "T7": t7,
        "T1": score_local("T1", ["in_scope", "category"]),
        "T2": score_local("T2", ["same_event"]),
    }  # fmt: skip
    scores["per_edition_cost"] = {m: per_edition_cost(scores, m) for m in HOSTED}
    (OUT / "scores.json").write_text(json.dumps(scores, indent=1, ensure_ascii=False) + "\n")
    write_csv(SHEETS / "T5-claims-sheet.csv", t5_sheet)
    if t6_sheet:
        write_csv(SHEETS / "T6-scripts-sheet.csv", t6_sheet)
    if t7_sheet:
        write_csv(SHEETS / "T7-clean-flags-review.csv", t7_sheet)
    print(json.dumps(scores, indent=1, ensure_ascii=False)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
