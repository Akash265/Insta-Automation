"""Editorial checks for an edition record (task P1-03).

Implements C01, C03, C04, C06, C07, C09, C10 and C11 from
docs/EDITORIAL_PIPELINE.md §7.3. C02 (live links) is `brief linkcheck`; C05, C08 and
C12 are later tasks.

Stages (how complete the record must be, docs/EDITORIAL_PIPELINE.md §14):
  draft      structure, sources, evidence for every material claim
  review     + verified claims, score and rationale, script, caption, rendered media
  published  + approved review, deployment record, publication record

The report lists flagged claims and uncertain sources first, then blocking issues,
then warnings (docs/EDITORIAL_PIPELINE.md §9.4).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from brief.edition.caption import caption_for_posting
from brief.edition.schema import CHECKLIST_KEYS, ClaimStatus, ClaimType, Edition, Story

Severity = Literal["blocking", "warning"]
Stage = Literal["draft", "review", "published"]
STAGES: tuple[Stage, ...] = ("draft", "review", "published")

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*")
SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")
ATTRIBUTION_RE = re.compile(
    r"\b(says|said|according to|reports?|reported|claims?|claimed|announced|states?|stated)\b",
    re.IGNORECASE,
)
VENDOR_BENCHMARK_CAVEAT_RE = re.compile(
    r"not independently verified|vendor-reported|self-reported|company-reported", re.IGNORECASE
)
DISCLOSURE_LABEL_RE = re.compile(
    r"\b(sponsored|advertisement|ad|affiliate|collaboration)\b", re.IGNORECASE
)
SAME_DAY_WORDS = ("today", "tonight", "this morning", "this afternoon", "this evening")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    message: str
    story_rank: int | None = None


@dataclass(frozen=True)
class Flag:
    kind: Literal["flagged_claim", "uncertain_source"]
    story_rank: int
    message: str


@dataclass
class ValidationReport:
    source: str
    stage: Stage
    issues: list[Issue] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "blocking"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def render(self) -> str:
        def where(rank: int | None) -> str:
            return f" story {rank}:" if rank is not None else ""

        lines = [f"brief validate: {self.source}  (stage: {self.stage})", ""]
        sections: list[tuple[str, list[str]]] = [
            (
                "FLAGGED CLAIMS",
                [
                    f"  - story {f.story_rank}: {f.message}"
                    for f in self.flags
                    if f.kind == "flagged_claim"
                ],
            ),
            (
                "UNCERTAIN SOURCES",
                [
                    f"  - story {f.story_rank}: {f.message}"
                    for f in self.flags
                    if f.kind == "uncertain_source"
                ],
            ),
            (
                "BLOCKING",
                [f"  - {i.code}{where(i.story_rank)} {i.message}" for i in self.blocking],
            ),
            (
                "WARNINGS",
                [f"  - {i.code}{where(i.story_rank)} {i.message}" for i in self.warnings],
            ),
        ]
        for title, items in sections:
            lines.append(f"{title} ({len(items)})" if items else f"{title}: none")
            lines.extend(items)
        verdict = "PASS" if self.ok else "FAIL"
        lines += [
            "",
            f"RESULT: {verdict} ({len(self.blocking)} blocking, "
            f"{len(self.warnings)} warning{'' if len(self.warnings) == 1 else 's'})",
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------------- loading


def load_edition(path: Path) -> tuple[Edition | None, list[Issue]]:
    """Parse an edition file. Schema problems become blocking C01 issues."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [Issue("C01", "blocking", f"cannot read edition JSON: {exc}")]
    return parse_edition(data)


def parse_edition(data: object) -> tuple[Edition | None, list[Issue]]:
    try:
        return Edition.model_validate(data), []
    except ValidationError as exc:
        issues = [
            Issue(
                "C01",
                "blocking",
                f"schema: {'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}",
            )
            for err in exc.errors()
        ]
        return None, issues


def validate_file(path: Path, stage: Stage) -> ValidationReport:
    edition, issues = load_edition(path)
    if edition is None:
        return ValidationReport(str(path), stage, issues)
    report = validate_edition(edition, stage)
    report.source = str(path)
    return report


def validate_edition(edition: Edition, stage: Stage) -> ValidationReport:
    report = ValidationReport("<edition>", stage)
    for check in (
        c01_completeness,
        c03_urls,
        c04_numbers,
        c06_time_words,
        c07_attribution,
        c09_lengths,
        c10_count_order,
        c11_disclosure,
    ):
        report.issues.extend(check(edition, stage))
    report.flags.extend(collect_flags(edition))
    return report


def _at_least(stage: Stage, minimum: Stage) -> bool:
    return STAGES.index(stage) >= STAGES.index(minimum)


def _story_texts(story: Story) -> list[str]:
    return [
        t
        for t in (
            story.headline,
            story.summary,
            story.why_it_matters,
            story.technical_notes,
            story.limitations,
            story.card_text,
            story.narration,
        )
        if t
    ]


def _material(story: Story) -> Iterator[tuple[int, object]]:
    for n, claim in enumerate(story.claims, start=1):
        if claim.materiality == "material" and claim.status is not ClaimStatus.WITHDRAWN:
            yield n, claim


# --------------------------------------------------------------------------- C01


def c01_completeness(edition: Edition, stage: Stage) -> Iterable[Issue]:
    """Audit-trail completeness for the stage (docs/EDITORIAL_PIPELINE.md §14)."""
    b: Severity = "blocking"
    for s in edition.stories:
        material = [
            c
            for c in s.claims
            if c.materiality == "material" and c.status is not ClaimStatus.WITHDRAWN
        ]
        if not material:
            yield Issue("C01", b, "no material claim recorded", s.rank)
        for n, c in enumerate(s.claims, start=1):
            if c.materiality == "material" and not c.evidence:
                yield Issue("C01", b, f"material claim {n} has no supporting evidence", s.rank)
        if s.published_at is None and s.event_at is None:
            yield Issue(
                "C01",
                b if _at_least(stage, "review") else "warning",
                "neither publication nor event timestamp is recorded",
                s.rank,
            )
        if not _at_least(stage, "review"):
            continue
        if s.score is None:
            yield Issue("C01", b, "story score is missing", s.rank)
        if not s.selected_reason:
            yield Issue("C01", b, "selection rationale is missing", s.rank)
        if not s.narration:
            yield Issue("C01", b, "narration is missing", s.rank)
        if not s.card_text:
            yield Issue("C01", b, "card text is missing", s.rank)
        for n, c in enumerate(s.claims, start=1):
            if c.materiality != "material" or c.status is ClaimStatus.WITHDRAWN:
                continue
            if c.status in (ClaimStatus.UNVERIFIED, ClaimStatus.UNSUPPORTED):
                yield Issue("C01", b, f"material claim {n} is '{c.status}', not verified", s.rank)
            if c.status is ClaimStatus.SUPPORTED:
                if not c.verified_by or c.verified_at is None:
                    yield Issue(
                        "C01", b, f"material claim {n} lacks verified_by/verified_at", s.rank
                    )
                if not any(e.stance == "supports" and e.source_tier <= 2 for e in c.evidence):
                    yield Issue(
                        "C01",
                        b,
                        f"material claim {n} has no supporting tier-1/2 evidence "
                        "(discovery-only sources cannot establish a claim)",
                        s.rank,
                    )
            if c.status is ClaimStatus.CONTESTED and not s.limitations:
                yield Issue(
                    "C01", b, f"material claim {n} is contested but limitations are empty", s.rank
                )

    if not _at_least(stage, "review"):
        return
    if edition.script is None:
        yield Issue("C01", b, "final script is missing")
    if not edition.caption:
        yield Issue("C01", b, "final caption is missing")
    if edition.review is None:
        yield Issue("C01", b, "review record (regime, reviewer, decision) is missing")
    media = edition.media
    if media is None or media.mp4 is None:
        yield Issue("C01", b, "rendered MP4 reference is missing")
    if media is None or not media.narration:
        yield Issue("C01", b, "narration audio references are missing")

    if not _at_least(stage, "published"):
        return
    review = edition.review
    if review is not None:
        if review.decision != "approved":
            yield Issue("C01", b, f"review decision is '{review.decision}', not approved")
        if not review.reviewer or review.reviewed_at is None:
            yield Issue("C01", b, "reviewer name and review time are required")
        unchecked = [k for k in CHECKLIST_KEYS if not review.checklist.get(k)]
        if unchecked:
            yield Issue("C01", b, f"review checklist incomplete: {', '.join(unchecked)}")
    dep = edition.deployment
    if dep is None or not dep.production_deploy_id or dep.deployed_at is None:
        yield Issue("C01", b, "deployment record (deploy id, time) is missing")
    elif dep.linkcheck != "pass":
        yield Issue("C01", b, f"link check is '{dep.linkcheck}', must be 'pass'")
    pub = edition.publication
    if pub is None or pub.published_at is None:
        yield Issue("C01", b, "publication record (method, time) is missing")
    elif pub.method == "manual" and not pub.permalink:
        yield Issue("C01", b, "manual upload needs the Instagram permalink")
    elif pub.method == "api" and not pub.media_id:
        yield Issue("C01", b, "API publication needs the Instagram media ID")


# --------------------------------------------------------------------------- C03


def _normalise_url(url: str) -> str:
    return url.rstrip(".,;:!?").rstrip("/")


def c03_urls(edition: Edition, stage: Stage) -> Iterable[Issue]:
    """Every URL in generated text must be a recorded source; evidence must be fetched."""
    known: set[str] = set()
    for s in edition.stories:
        known.add(_normalise_url(s.primary_source_url))
        known.update(_normalise_url(u) for u in s.supporting_source_urls)
        for c in s.claims:
            known.update(_normalise_url(e.url) for e in c.evidence)
    for extra in (
        edition.issue_url,
        edition.deployment.preview_url if edition.deployment else None,
        edition.publication.permalink if edition.publication else None,
    ):
        if extra:
            known.add(_normalise_url(extra))

    def scan(text: str | None, rank: int | None, label: str) -> Iterator[Issue]:
        for url in URL_RE.findall(text or ""):
            if _normalise_url(url) not in known:
                yield Issue("C03", "blocking", f"{label} contains an unrecorded URL: {url}", rank)

    yield from scan(edition.caption, None, "caption")
    yield from scan(edition.daily_thesis, None, "daily thesis")
    if edition.script:
        yield from scan(edition.script.hook, None, "script hook")
        yield from scan(edition.script.outro, None, "script outro")
    for s in edition.stories:
        for text in _story_texts(s):
            yield from scan(text, s.rank, "story text")
        for n, c in enumerate(s.claims, start=1):
            for e in c.evidence:
                if e.retrieved_at is None:
                    yield Issue(
                        "C03",
                        "blocking",
                        f"claim {n} evidence was not fetched (no retrieved_at): {e.url}",
                        s.rank,
                    )


# --------------------------------------------------------------------------- C04


def _numbers(text: str) -> set[str]:
    found = set()
    for raw in NUMBER_RE.findall(text):
        value = raw.replace(",", "")
        if re.fullmatch(r"(19|20)\d\d", value):  # calendar years are not checked
            continue
        found.add(value)
    return found


def c04_numbers(edition: Edition, stage: Stage) -> Iterable[Issue]:
    """Numbers in story copy must appear in that story's claims or evidence excerpts."""
    for s in edition.stories:
        pool = set()
        for c in s.claims:
            pool |= _numbers(c.claim_text)
            for e in c.evidence:
                pool |= _numbers(e.excerpt)
        for text in (s.headline, s.summary, s.card_text, s.narration):
            for number in sorted(_numbers(text or "") - pool):
                yield Issue(
                    "C04",
                    "blocking",
                    f"number {number!r} is not in any claim or evidence excerpt",
                    s.rank,
                )


# --------------------------------------------------------------------------- C06


def _has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE) is not None


def c06_time_words(edition: Edition, stage: Stage) -> Iterable[Issue]:
    """Time words must agree with the event date (not the article's publication date)."""
    tz = ZoneInfo(edition.timezone)
    issue_day: date = edition.issue_date
    for s in edition.stories:
        text = " ".join(t for t in (s.headline, s.summary, s.card_text, s.narration) if t)
        event_day = s.event_at.astimezone(tz).date() if s.event_at else None
        used = [w for w in (*SAME_DAY_WORDS, "yesterday", "this week") if _has_phrase(text, w)]
        if used and event_day is None:
            yield Issue(
                "C06", "blocking", f"uses {used[0]!r} but the event date is unknown", s.rank
            )
            continue
        if event_day is None:
            continue
        for word in used:
            if word in SAME_DAY_WORDS and event_day != issue_day:
                yield Issue(
                    "C06",
                    "blocking",
                    f"says {word!r} but the event was on {event_day.isoformat()}",
                    s.rank,
                )
            if word == "yesterday" and event_day != issue_day - timedelta(days=1):
                yield Issue(
                    "C06",
                    "blocking",
                    f"says 'yesterday' but the event was on {event_day.isoformat()}",
                    s.rank,
                )
            if word == "this week":
                cutoff = edition.cutoff_at
                event_at: datetime = s.event_at  # type: ignore[assignment]
                if not timedelta(0) <= cutoff - event_at <= timedelta(days=7):
                    yield Issue(
                        "C06",
                        "blocking",
                        "says 'this week' but the event is not within 7 days",
                        s.rank,
                    )
        actual = WEEKDAYS[event_day.weekday()]
        for day in WEEKDAYS:
            if day != actual and _has_phrase(text, f"on {day}"):
                yield Issue(
                    "C06",
                    "warning",
                    f"mentions 'on {day.title()}' but the event was on {actual.title()} "
                    "(fine only if it refers to a different, future event)",
                    s.rank,
                )


# --------------------------------------------------------------------------- C07


def c07_attribution(edition: Edition, stage: Stage) -> Iterable[Issue]:
    """Vendor claims must be attributed; vendor benchmarks need a caveat."""
    for s in edition.stories:
        types = {c.claim_type for _, c in _material(s)}  # type: ignore[attr-defined]
        if not types & {ClaimType.VENDOR_CLAIM, ClaimType.BENCHMARK_VENDOR}:
            continue
        copy = " ".join(t for t in (s.summary, s.narration) if t)
        if not ATTRIBUTION_RE.search(copy) and f"per {s.publisher}".lower() not in copy.lower():
            yield Issue(
                "C07",
                "blocking",
                "vendor claim is not attributed (e.g. 'the company says')",
                s.rank,
            )
        if ClaimType.BENCHMARK_VENDOR in types and not VENDOR_BENCHMARK_CAVEAT_RE.search(
            s.limitations or ""
        ):
            yield Issue(
                "C07",
                "blocking",
                "vendor benchmark needs a limitation such as 'not independently verified'",
                s.rank,
            )


# --------------------------------------------------------------------------- C09


def _sentences(text: str) -> int:
    return len(SENTENCE_END_RE.findall(text.strip())) or (1 if text.strip() else 0)


def _words(text: str | None) -> int:
    return len((text or "").split())


def c09_lengths(edition: Edition, stage: Stage) -> Iterable[Issue]:
    w: Severity = "warning"
    for s in edition.stories:
        if s.card_text and len(s.card_text) > 90:
            yield Issue("C09", w, f"card text is {len(s.card_text)} chars (max 90)", s.rank)
        n = _sentences(s.summary)
        if not 2 <= n <= 4:
            yield Issue("C09", w, f"summary has {n} sentences (expected 2-4)", s.rank)
    if edition.caption:
        posted = len(caption_for_posting(edition))
        if posted > 2200:
            yield Issue("C09", w, f"caption with hashtags is {posted} chars (max 2,200)")
    if len(edition.hashtags) > 5:
        yield Issue("C09", w, f"{len(edition.hashtags)} hashtags (max 5)")
    if edition.script and all(s.narration for s in edition.stories):
        total = (
            _words(edition.script.hook)
            + sum(_words(s.narration) for s in edition.stories)
            + _words(edition.script.outro)
        )
        low = 90 if edition.is_quiet_day else 160
        if not low <= total <= 230:
            yield Issue("C09", w, f"narration is {total} words (expected {low}-230)")


# --------------------------------------------------------------------------- C10


def c10_count_order(edition: Edition, stage: Stage) -> Iterable[Issue]:
    b: Severity = "blocking"
    stories = edition.stories
    if edition.status != "skipped" and not 1 <= len(stories) <= 7:
        yield Issue("C10", b, f"{len(stories)} stories (expected 1-7)")
    ranks = [s.rank for s in stories]
    if sorted(ranks) != list(range(1, len(stories) + 1)):
        yield Issue("C10", b, f"ranks must be 1..{len(stories)} with no gaps or repeats: {ranks}")
    ids = [s.story_id for s in stories]
    if len(set(ids)) != len(ids):
        yield Issue("C10", b, "story_id values must be unique")
    if edition.caption and stories:
        lines = edition.caption.splitlines()
        positions = []
        for rank in sorted(ranks):
            idx = next(
                (i for i, ln in enumerate(lines) if re.match(rf"^\s*{rank}[.)]\s", ln)), None
            )
            if idx is None:
                yield Issue("C10", b, f"caption has no numbered line for story {rank}")
            positions.append(idx)
        found = [p for p in positions if p is not None]
        if found != sorted(found):
            yield Issue("C10", b, "caption lists the stories out of rank order")


# --------------------------------------------------------------------------- C11


def c11_disclosure(edition: Edition, stage: Stage) -> Iterable[Issue]:
    sponsored = [s for s in edition.stories if s.sponsored]
    if not (edition.sponsor_flag or sponsored):
        return
    for s in sponsored:
        if not s.disclosure:
            yield Issue("C11", "blocking", "sponsored story has no disclosure text", s.rank)
    if not DISCLOSURE_LABEL_RE.search(edition.caption or ""):
        yield Issue(
            "C11", "blocking", "caption lacks a disclosure label (Sponsored / Ad / Affiliate)"
        )


# --------------------------------------------------------------------------- flags


def collect_flags(edition: Edition) -> list[Flag]:
    flags: list[Flag] = []
    for s in edition.stories:
        if s.source_tier == 3:
            flags.append(
                Flag(
                    "uncertain_source",
                    s.rank,
                    f"story's own source is discovery-only (tier 3): {s.publisher}",
                )
            )
        for n, c in enumerate(s.claims, start=1):
            if c.materiality != "material" or c.status is ClaimStatus.WITHDRAWN:
                continue
            short = c.claim_text if len(c.claim_text) <= 80 else c.claim_text[:77] + "..."
            if c.status is not ClaimStatus.SUPPORTED or c.confidence == "low":
                label = (
                    c.status.value if c.status is not ClaimStatus.SUPPORTED else "low confidence"
                )
                flags.append(Flag("flagged_claim", s.rank, f"claim {n} [{label}]: {short}"))
            supports = [e for e in c.evidence if e.stance == "supports"]
            if (
                supports
                and all(e.source_tier == 2 for e in supports)
                and len({e.publisher for e in supports}) == 1
            ):
                flags.append(
                    Flag(
                        "uncertain_source",
                        s.rank,
                        f"claim {n} rests on a single tier-2 source ({supports[0].publisher})",
                    )
                )
            if any(e.source_tier == 3 for e in c.evidence):
                flags.append(
                    Flag(
                        "uncertain_source",
                        s.rank,
                        f"claim {n} cites a discovery-only (tier 3) source",
                    )
                )
            if any(e.stance == "contradicts" for e in c.evidence):
                flags.append(Flag("flagged_claim", s.rank, f"claim {n} has contradicting evidence"))
    return flags
