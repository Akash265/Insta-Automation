"""Pre-registration guards (P1-25, P1-37): frozen texts in docs/gates/phase-1.md.

The thresholds must be an exact copy of VALIDATION_EXPERIMENT §3, and the rubric
(EDITORIAL_PIPELINE §5-§6) must match the fingerprint recorded at sign-off. A failure here
means a frozen text changed: re-sign before Day 1, and never change it during the experiment.
"""

from __future__ import annotations

import hashlib
import re

from tests.conftest import ROOT

DOCS = ROOT / "docs"
GATE = (DOCS / "gates" / "phase-1.md").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end)]


def test_thresholds_are_an_exact_copy_of_section_3() -> None:
    v = (DOCS / "VALIDATION_EXPERIMENT.md").read_text(encoding="utf-8")
    section3 = _between(v, "## 3. Hypotheses", "## 4. Daily workflow").split("\n", 1)[1]
    copied = _between(
        GATE, "<!-- BEGIN PRE-REGISTERED §3 (do not edit) -->", "<!-- END PRE-REGISTERED §3 -->"
    ).split("\n", 1)[1]
    assert copied.strip("\n") == section3.strip("\n")
    for threshold in ("≥ 10 of 14 days", "**≥ 3.8**", "≥ 13/14 renders", "≤ 130", "score ≥ 55"):
        assert threshold in copied


def test_rubric_matches_the_signed_fingerprint() -> None:
    e = (DOCS / "EDITORIAL_PIPELINE.md").read_text(encoding="utf-8")
    rubric = _between(e, "## 5. Ranking", "## 7. Claims")
    recorded = re.search(r"`sha256 ([0-9a-f]{64})`", GATE)
    assert recorded, "no rubric fingerprint in docs/gates/phase-1.md"
    assert hashlib.sha256(rubric.encode("utf-8")).hexdigest() == recorded.group(1), (
        "EDITORIAL_PIPELINE §5-§6 changed after the rubric was recorded; re-sign (P1-37)"
    )
