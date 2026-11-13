"""P1-03: `brief validate` checks — each has a passing and a failing case."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from brief.cli import app
from brief.edition.checks import Stage, ValidationReport, parse_edition, validate_edition
from tests.conftest import FIXTURES

Data = dict[str, Any]


def run(data: Data, stage: Stage = "published") -> ValidationReport:
    edition, issues = parse_edition(data)
    if edition is None:
        report = ValidationReport("<test>", stage, issues)
        return report
    return validate_edition(edition, stage)


def codes(report: ValidationReport, severity: str = "blocking") -> set[str]:
    return {i.code for i in report.issues if i.severity == severity}


# --------------------------------------------------------------------- baselines


def test_fixtures_pass_cleanly(normal: Data, quiet: Data) -> None:
    for data in (normal, quiet):
        report = run(data)
        assert report.ok and not report.warnings, report.render()


def test_template_passes_at_draft_but_not_review() -> None:
    import json

    data = json.loads(Path("editions/_template.json").read_text(encoding="utf-8"))
    assert run(data, "draft").ok
    assert not run(data, "review").ok


# --------------------------------------------------------------------- C01: audit trail


def _drop_story_key(key: str) -> Callable[[Data], None]:
    def mutate(d: Data) -> None:
        del d["stories"][0][key]

    return mutate


def _set(path: list[Any], value: Any) -> Callable[[Data], None]:
    def mutate(d: Data) -> None:
        target: Any = d
        for p in path[:-1]:
            target = target[p]
        target[path[-1]] = value

    return mutate


def _no_timestamps(d: Data) -> None:
    s = d["stories"][1]
    s["published_at"] = None
    s["event_at"] = None
    s["event_at_basis"] = "unknown"


AUDIT_TRAIL_MUTATIONS: dict[str, Callable[[Data], None]] = {
    "01 source URLs": _drop_story_key("primary_source_url"),
    "02 publisher and source type": _drop_story_key("source_type"),
    "03 publication and event timestamps": _no_timestamps,
    "04 collection timestamp": _drop_story_key("collected_at"),
    "05 material claims": _set(["stories", 0, "claims"], []),
    "06 evidence for each material claim": _set(["stories", 0, "claims", 0, "evidence"], []),
    "07 verification status": _set(["stories", 0, "claims", 0, "status"], "unverified"),
    "08 score and selection rationale": _set(["stories", 0, "selected_reason"], None),
    "09 reviewer decision": _set(["review", "decision"], "pending"),
    "10 final script": _set(["script"], None),
    "11 final caption": _set(["caption"], None),
    "12 media references": _set(["media", "mp4"], None),
    "13 deployment record": _set(["deployment"], None),
    "14 publication record": _set(["publication"], None),
}


@pytest.mark.parametrize("item", sorted(AUDIT_TRAIL_MUTATIONS))
def test_every_audit_trail_item_is_required_when_published(normal: Data, item: str) -> None:
    AUDIT_TRAIL_MUTATIONS[item](normal)
    report = run(normal, "published")
    assert "C01" in codes(report), f"{item}: {report.render()}"


def test_c01_stage_gating(normal: Data) -> None:
    normal["deployment"] = None
    assert run(normal, "review").ok  # deployment is not needed before publication
    assert not run(normal, "published").ok


def test_c01_discovery_only_evidence_cannot_establish_a_claim(normal: Data) -> None:
    normal["stories"][0]["claims"][0]["evidence"][0]["source_tier"] = 3
    report = run(normal)
    assert any("discovery-only" in i.message for i in report.blocking)


def test_c01_manual_upload_needs_permalink(normal: Data) -> None:
    normal["publication"] = {
        "platform": "instagram",
        "method": "manual",
        "published_at": "2026-11-20T14:30:00+00:00",
    }
    assert "C01" in codes(run(normal))
    normal["publication"]["permalink"] = "https://www.instagram.com/reel/EXAMPLE/"
    assert run(normal).ok


# --------------------------------------------------------------------- C03


def test_c03_unrecorded_url_in_copy(normal: Data) -> None:
    normal["stories"][0]["narration"] += " More at https://example.com/not-a-recorded-source."
    assert "C03" in codes(run(normal))


def test_c03_recorded_url_is_fine(normal: Data) -> None:
    normal["stories"][0]["why_it_matters"] += " Source: https://example.com/labs/news/nimbus-2."
    assert run(normal).ok


def test_c03_evidence_must_be_fetched(normal: Data) -> None:
    normal["stories"][2]["claims"][0]["evidence"][0]["retrieved_at"] = None
    assert "C03" in codes(run(normal, "draft"))


# --------------------------------------------------------------------- C04


def test_c04_unbacked_number_blocks(normal: Data) -> None:
    normal["stories"][1]["narration"] = normal["stories"][1]["narration"].replace("61%", "64%")
    report = run(normal)
    assert "C04" in codes(report)
    assert any("'64'" in i.message for i in report.blocking)


def test_c04_years_and_backed_numbers_pass(normal: Data) -> None:
    normal["stories"][1]["narration"] += " Expect follow-up work in 2027."
    assert "C04" not in codes(run(normal))


@pytest.mark.parametrize("phrase", ["on November 19", "on 19 November", "on Nov. 19th"])
def test_c04_day_of_the_storys_own_date_passes(normal: Data, phrase: str) -> None:
    # story 2's event and publication time is 19 Nov 2026 19:30 IST
    normal["stories"][1]["narration"] += f" It was posted {phrase}."
    assert "C04" not in codes(run(normal))


def test_c04_wrong_date_still_blocks(normal: Data) -> None:
    normal["stories"][1]["narration"] += " It was posted on November 18."
    assert any(i.code == "C04" and "'18'" in i.message for i in run(normal).blocking)


def test_c04_day_number_outside_a_date_is_still_checked(normal: Data) -> None:
    normal["stories"][1]["narration"] += " It has 19 authors."
    assert any(i.code == "C04" and "'19'" in i.message for i in run(normal).blocking)


def test_c04_number_words_in_claims_back_digits(normal: Data) -> None:
    story = normal["stories"][1]
    story["claims"][1]["claim_text"] += " It used ten tasks and a sixty-five-page appendix."
    story["narration"] += " It used 10 tasks and a 65-page appendix."
    assert "C04" not in codes(run(normal))
    story["narration"] += " It cost 11 dollars."
    assert any(i.code == "C04" and "'11'" in i.message for i in run(normal).blocking)


# --------------------------------------------------------------------- C06


def test_c06_today_must_match_event_day(normal: Data) -> None:
    normal["stories"][1]["narration"] += " The authors released it today."  # event was 19 Nov
    assert "C06" in codes(run(normal))


def test_c06_time_word_without_event_date(normal: Data) -> None:
    s = normal["stories"][3]
    s["event_at"] = None
    s["event_at_basis"] = "unknown"
    s["narration"] += " It went live today."
    assert "C06" in codes(run(normal))


def test_c06_weekend_story_on_monday_passes(quiet: Data) -> None:
    assert "C06" not in codes(run(quiet), "warning")


def test_c06_wrong_weekday_is_a_warning(quiet: Data) -> None:
    s = quiet["stories"][0]
    s["narration"] = s["narration"].replace("On Saturday", "On Sunday")
    report = run(quiet)
    assert report.ok and "C06" in codes(report, "warning")


# --------------------------------------------------------------------- C07


def test_c07_vendor_claim_needs_attribution(normal: Data) -> None:
    s = normal["stories"][0]
    s["summary"] = (
        "Example Labs released Nimbus-2 through its public API today. "
        "Nimbus-2 handles 200,000 tokens of context at $3 per million input tokens."
    )
    s["narration"] = (
        "Example Labs made Nimbus-2 available through its public API today. "
        "It handles 200,000 tokens of context, priced from $3 per million input "
        "tokens."
    )
    assert "C07" in codes(run(normal))


def test_c07_vendor_benchmark_needs_caveat(normal: Data) -> None:
    s = normal["stories"][1]
    s["claims"][1]["claim_type"] = "benchmark_vendor"
    s["limitations"] = "Preprint."
    assert "C07" in codes(run(normal))
    s["limitations"] = "Preprint; vendor-reported result, not independently verified."
    assert "C07" not in codes(run(normal))


# --------------------------------------------------------------------- C09 (warnings)


def test_c09_long_card_text_is_a_warning(normal: Data) -> None:
    normal["stories"][0]["card_text"] = "x" * 95
    report = run(normal)
    assert report.ok and "C09" in codes(report, "warning")


def test_c09_too_many_hashtags(normal: Data) -> None:
    normal["hashtags"] = ["#a", "#b", "#c", "#d", "#e", "#f"]
    assert "C09" in codes(run(normal), "warning")


# --------------------------------------------------------------------- C10


def test_c10_duplicate_rank(normal: Data) -> None:
    normal["stories"][1]["rank"] = 1
    assert "C10" in codes(run(normal))


def test_c10_caption_order(normal: Data) -> None:
    lines = normal["caption"].splitlines()
    i1 = next(i for i, ln in enumerate(lines) if ln.startswith("1. "))
    i2 = next(i for i, ln in enumerate(lines) if ln.startswith("2. "))
    lines[i1], lines[i2] = lines[i2], lines[i1]
    normal["caption"] = "\n".join(lines)
    assert "C10" in codes(run(normal))


def test_c10_no_stories(normal: Data) -> None:
    normal["stories"] = []
    assert "C10" in codes(run(normal, "draft"))


# --------------------------------------------------------------------- C11


def test_c11_sponsor_needs_disclosure(normal: Data) -> None:
    normal["sponsor_flag"] = True
    assert "C11" in codes(run(normal))
    normal["caption"] += "\nSponsored: Example Sponsor supports this edition."
    assert "C11" not in codes(run(normal))


# --------------------------------------------------------------------- report order + CLI


def test_report_lists_flags_before_failed_checks(normal: Data) -> None:
    s = normal["stories"][3]
    s["claims"][0]["status"] = "contested"  # flagged claim; limitations empty -> C01 blocking
    s["claims"][0]["evidence"] = s["claims"][0]["evidence"][:1]  # single tier-2 source
    normal["stories"][0]["card_text"] = "x" * 95  # warning
    text = run(normal).render()
    order = [
        text.index(h)
        for h in ("FLAGGED CLAIMS (", "UNCERTAIN SOURCES (", "BLOCKING (", "WARNINGS (")
    ]
    assert order == sorted(order), text


def test_cli_exit_codes(tmp_path: Path, normal: Data) -> None:
    runner = CliRunner()
    good = runner.invoke(app, ["validate", str(FIXTURES / "normal.json"), "--stage", "published"])
    assert good.exit_code == 0, good.output

    import json

    normal["stories"][0]["narration"] += " See https://example.com/unrecorded."
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps(normal), encoding="utf-8")
    bad = runner.invoke(app, ["validate", str(bad_file), "--stage", "published"])
    assert bad.exit_code == 1 and "C03" in bad.output

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert runner.invoke(app, ["validate", str(broken)]).exit_code == 1

    assert runner.invoke(app, ["validate", str(bad_file), "--stage", "final"]).exit_code != 0
