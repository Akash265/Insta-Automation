"""`brief script draft`: an LLM first draft of an edition's copy (task P1-13, optional).

The draft is written only from claims the editor has already marked `supported`, on the
T6 route in `config/llm_routes.yaml` (Haiku 5.5 with `script.v2`, P1-09). The model gets
no URLs and must return none. Output is schema-checked; one bounded repair is allowed
(CLAUDE.md), after which the command fails and the editor writes the copy by hand.
The editorial checks then run on the result; the editor reviews every word either way.
Every call, including a failed one, is in the usage ledger.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml  # type: ignore[import-untyped]

from brief.edition.schema import Claim, ClaimStatus, Edition, Story
from brief.llm.client import (
    DEFAULT_ROUTES,
    AnthropicJSON,
    InvalidOutputError,
    LLMError,
    ModelInfo,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"
TASK = "T6_script"
MAX_TOKENS = 10_000  # P1-09: Haiku used ~7k output tokens per edition, thinking included
URL_IN_TEXT_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
STORY_FIELDS = ("headline", "summary", "why_it_matters", "limitations", "card_text", "narration")


class DraftError(RuntimeError):
    """The draft could not be produced; the editor writes the copy by hand."""


@dataclass(frozen=True)
class Route:
    task: str
    model: str
    effort: str
    prompt: str


def load_route(task: str, models: dict[str, ModelInfo], path: Path = DEFAULT_ROUTES) -> Route:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = (data.get("routes") or {}).get(task)
    if not raw or not raw.get("prompt"):
        raise DraftError(f"{task} has no route with a prompt in {path}")
    model = str(raw["primary"])
    info = models.get(model)
    if info is None:
        raise DraftError(f"{task} routes to {model!r}, which is not a configured model")
    if info.evaluation_only:
        raise DraftError(f"{task} routes to {model}, which is for evaluation only")
    return Route(task, model, str(raw.get("effort", "medium")), str(raw["prompt"]))


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}  # fmt: skip


SCHEMA = _obj(
    {
        "hook": {"type": "string"},
        "outro": {"type": "string"},
        "stories": {
            "type": "array",
            "items": _obj(
                {"rank": {"type": "integer"}, "story_id": {"type": "string"}}
                | {f: {"type": "string"} for f in STORY_FIELDS}
            ),
        },
    }
)


def _supported(story: Story) -> list[Claim]:
    return [c for c in story.claims if c.status is ClaimStatus.SUPPORTED]


def _attr(value: str) -> str:
    return value.replace('"', "'").replace("<", "(").replace(">", ")")


def script_input(edition: Edition) -> str:
    """The stories and their supported claims, as delimited data (no URLs)."""
    if not edition.stories:
        raise DraftError("the edition has no stories")
    missing = [s.rank for s in edition.stories if not _supported(s)]
    if missing:
        raise DraftError(
            f"stories {missing} have no claim marked 'supported'; verify claims before drafting"
        )
    tz = ZoneInfo(edition.timezone)
    parts = [f'<stories edition_date="{edition.issue_date.isoformat()}">']
    for s in sorted(edition.stories, key=lambda x: x.rank):
        dates = " ".join(
            f'{label}="{value.astimezone(tz).date().isoformat()}"'
            for label, value in (("event", s.event_at), ("published", s.published_at))
            if value is not None
        )
        claims = "\n".join(f"  - [{c.claim_type}] {c.claim_text}" for c in _supported(s))
        parts.append(
            f'<story rank="{s.rank}" story_id="{_attr(s.story_id)}" category="{s.category}" '
            f'publisher="{_attr(s.publisher)}" {dates}>\n'
            f"Verified claims:\n{claims}\n</story>"
        )
    parts.append("</stories>")
    return "\n".join(parts)


def make_validator(edition: Edition) -> Callable[[dict[str, Any]], None]:
    expected = sorted((s.rank, s.story_id) for s in edition.stories)

    def check(data: dict[str, Any]) -> None:
        got = sorted((int(st["rank"]), str(st["story_id"])) for st in data["stories"])
        if got != expected:
            raise ValueError(f"stories {got} do not match the edition's {expected}")
        if not str(data["hook"]).strip() or not str(data["outro"]).strip():
            raise ValueError("hook and outro must not be empty")
        texts = [str(data["hook"]), str(data["outro"])]
        for st in data["stories"]:
            for f in STORY_FIELDS:
                if f != "limitations" and not str(st[f]).strip():
                    raise ValueError(f"story {st['rank']} has an empty {f}")
                texts.append(str(st[f]))
        if any(URL_IN_TEXT_RE.search(t) for t in texts):
            raise ValueError("the copy contains a URL; links come from the evidence only")

    return check


@dataclass(frozen=True)
class Draft:
    data: dict[str, Any]
    model: str
    attempts: int
    cost_usd: float  # of the accepted call; every call is in the usage ledger


def draft_script(
    edition: Edition,
    client: AnthropicJSON,
    route: Route,
    prompts_dir: Path = PROMPTS_DIR,
) -> Draft:
    """Draft the copy, with at most one repair after invalid output."""
    system = (prompts_dir / f"{route.prompt}.md").read_text(encoding="utf-8")
    user = script_input(edition)
    validate = make_validator(edition)
    operation = f"script_draft:{edition.issue_key}"

    def call(prompt: str, op: str) -> Any:
        return client.complete(
            route.model, system, prompt, SCHEMA, op,
            max_tokens=MAX_TOKENS, effort=route.effort, validate=validate,
        )  # fmt: skip

    try:
        r = call(user, operation)
        return Draft(r.data, route.model, 1, r.cost_usd)
    except InvalidOutputError as first:
        reason = str(first)
    repair = (
        f"{user}\n\n<rejected_reason>{reason}</rejected_reason>\n"
        "Your previous reply was rejected for the reason above. Reply again with the "
        "complete JSON object, following every rule."
    )
    try:
        r = call(repair, f"{operation}:repair")
    except InvalidOutputError as second:
        msg = f"draft failed after 1 repair ({second}); write the copy by hand"
        raise DraftError(msg) from second
    except LLMError as exc:
        raise DraftError(f"repair call failed ({exc}); write the copy by hand") from exc
    return Draft(r.data, route.model, 2, r.cost_usd)


def apply_draft(raw: dict[str, Any], draft: Draft) -> dict[str, Any]:
    """A copy of the raw edition JSON with the drafted copy filled in (script version +1)."""
    by_id = {st["story_id"]: st for st in draft.data["stories"]}
    stories = []
    for story in raw.get("stories", []):
        s = dict(story)
        new = by_id[s["story_id"]]
        for f in STORY_FIELDS:
            value = str(new[f]).strip()
            s[f] = value if value or f != "limitations" else None
        stories.append(s)
    old = raw.get("script") or {}
    script = {
        **old,
        "version": int(old.get("version", 0)) + 1,
        "hook": str(draft.data["hook"]).strip(),
        "outro": str(draft.data["outro"]).strip(),
    }
    return {**raw, "stories": stories, "script": script}


def render_text(data: dict[str, Any]) -> str:
    lines = [f"Hook: {data['hook']}"]
    for st in sorted(data["stories"], key=lambda x: int(x["rank"])):
        lines += [
            f"\nStory {st['rank']}: {st['headline']}",
            f"  Card: {st['card_text']}",
            f"  Narration: {st['narration']}",
            f"  Summary: {st['summary']}",
            f"  Why it matters: {st['why_it_matters']}",
            f"  Limitations: {st['limitations'] or '-'}",
        ]
    lines.append(f"\nOutro: {data['outro']}")
    return "\n".join(lines)
