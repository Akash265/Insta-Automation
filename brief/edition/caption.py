"""Caption generator (task P1-13, caption part).

The caption is generated from the same edition record as the page and the Reel, so
they cannot drift apart. The format is fixed because check C10 relies on it:

    AI Daily Brief, Friday 20 November 2026[ (quiet day)]

    1. Headline (Publisher)
    2. Headline (Publisher)

    [Sponsored: <disclosure>]
    Full stories and original links: link in bio.

Hashtags stay in the record's `hashtags` field and are appended only for posting.
The caption never contains URLs (Instagram captions don't link; check C03).
"""

from __future__ import annotations

from brief.edition.schema import Edition

BRAND = "AI Daily Brief"
CALL_TO_ACTION = "Full stories and original links: link in bio."
GENERIC_SPONSOR_LINE = "Sponsored: this edition includes a sponsored segment."
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip


def caption_title(edition: Edition) -> str:
    d = edition.issue_date
    title = f"{BRAND}, {_WEEKDAYS[d.weekday()]} {d.day} {_MONTHS[d.month - 1]} {d.year}"
    return f"{title} (quiet day)" if edition.is_quiet_day else title


def build_caption(edition: Edition) -> str:
    """Deterministic caption from the edition record (same record → same text)."""
    lines = [caption_title(edition), ""]
    stories = sorted(edition.stories, key=lambda s: s.rank)
    lines += [f"{s.rank}. {s.headline} ({s.publisher})" for s in stories]
    lines.append("")
    disclosures = [f"Sponsored: {s.disclosure}" for s in stories if s.sponsored and s.disclosure]
    if edition.sponsor_flag and not disclosures:
        disclosures = [GENERIC_SPONSOR_LINE]
    lines += disclosures
    lines.append(CALL_TO_ACTION)
    return "\n".join(lines)


def caption_for_posting(edition: Edition) -> str:
    """The text to paste into Instagram: the recorded caption plus hashtags."""
    caption = edition.caption or build_caption(edition)
    tags = " ".join(edition.hashtags)
    return f"{caption}\n\n{tags}" if tags else caption
