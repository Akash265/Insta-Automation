"""P1-14 and P1-19: Phase 1 and experiment reports, thresholds and the audit sampler."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from brief.budget import IST
from brief.cli import app
from brief.experiment.errorlog import COLUMNS, append_error, append_resolution, init_anchor
from brief.experiment.report import THRESHOLDS, experiment_report, phase1_report
from brief.experiment.sampler import sample_story_ranks
from tests.conftest import FIXTURES

START = date(2026, 12, 1)
NOW = datetime(2026, 12, 10, 9, 0, tzinfo=IST)


def test_thresholds_match_preregistration() -> None:
    assert THRESHOLDS == {
        "complete_editions_min": 10, "h1_days_with_5_eligible_min": 10,
        "h1_min_eligible_every_day": 3, "h2_evidence_share_min": 1.0, "h2_unresolved_max": 0,
        "h2_total_material_max": 1, "h2_minor_per_10_max": 3, "h3_median_all_max": 150,
        "h3_median_last5_max": 130, "h4_d1_mean_min": 3.8, "h4_response_rate_min": 0.5,
        "h4_d5_share_min": 0.6, "h5_w1_share_min": 0.5, "h5_misses_max": 2,
        "h6_render_ok_share_min": 0.9, "h6_deploy_share_min": 1.0,
        "w2_share_follow": 0.5, "w2_share_stop": 0.3,
    }  # fmt: skip


def test_sampler_is_reproducible_and_in_range() -> None:
    first = sample_story_ranks("ADB-2026-12-03", [1, 2, 3, 4, 5])
    assert first == sample_story_ranks("ADB-2026-12-03", [5, 4, 3, 2, 1])
    assert len(first) == 2 and set(first) <= {1, 2, 3, 4, 5}
    assert sample_story_ranks("ADB-2026-12-03", [1]) == [1]


def make_editions(
    directory: Path, minutes: int = 120, manual_fix_days: tuple[int, ...] = ()
) -> None:
    """14 experiment editions built from the normal fixture, every date shifted."""
    text = (FIXTURES / "normal.json").read_text(encoding="utf-8")
    directory.mkdir(parents=True, exist_ok=True)
    for day in range(1, 15):
        d = START + timedelta(days=day - 1)
        shifted = text.replace("2026-11-19", (d - timedelta(days=1)).isoformat()).replace(
            "2026-11-20", d.isoformat()
        )
        data: dict[str, Any] = json.loads(shifted)
        data["experiment"].update(
            day=day, eligible_count=6, render_attempts=1,
            render_manual_fix=day in manual_fix_days,
        )  # fmt: skip
        log = data["production_log"]
        for k in (
            "minutes_research",
            "minutes_verify",
            "minutes_script",
            "minutes_render",
            "minutes_site",
            "minutes_review",
            "minutes_publish",
        ):
            log[k] = 0
        log["minutes_research"] = minutes
        (directory / f"{d.isoformat()}.json").write_text(json.dumps(data), encoding="utf-8")


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def make_experiment(directory: Path, d1: int = 4, responders: int = 8) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    codes = [f"P{n:02d}" for n in range(1, 11)]
    write_csv(
        directory / "panel-roster.csv",
        ["panel_code", "segment", "joined_on", "active"],
        [[c, "developer", "2026-11-25", "true"] for c in codes],
    )
    responses = []
    for day in range(1, 15):
        d = (START + timedelta(days=day - 1)).isoformat()
        for c in codes[:responders]:
            weekly = day in (7, 14)
            responses.append(
                [
                    d,
                    c,
                    "true",
                    d1,
                    4,
                    4,
                    4,
                    5,
                    "",
                    4 if weekly else "",
                    4 if weekly else "",
                    4 if weekly else "",
                    "",
                ]
            )
    write_csv(
        directory / "panel-responses.csv",
        [
            "date",
            "panel_code",
            "watched_full",
            "D1",
            "D2",
            "D3",
            "D4",
            "D5",
            "D6",
            "W1",
            "W2",
            "W3",
            "W4",
        ],
        responses,
    )
    write_csv(
        directory / "coverage-misses.csv",
        ["date", "reference_roundup", "missed_story_url", "met_our_rules", "reason"],
        [["2026-12-02", "Roundup A", "https://example.com/missed", "Y", "not in sources"]],
    )
    audits = [
        [
            (START + timedelta(days=i)).isoformat(),
            f"ADB-{(START + timedelta(days=i))}",
            2,
            "next_morning",
            "independent",
            "claim",
            "https://example.com",
            "supported",
            "none",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        for i in range(11)
    ]
    write_csv(
        directory / "audit-log.csv",
        [
            "date",
            "issue_key",
            "story_rank",
            "audit_type",
            "auditor_type",
            "claim_text",
            "source_url_checked",
            "finding",
            "severity",
            "evidence_url",
            "evidence_excerpt",
            "escalated_at",
            "resolution",
            "correction_ref",
            "notes",
        ],
        audits,
    )
    log = directory / "error-log.csv"
    init_anchor(log, NOW)
    append_error(
        log,
        issue_key="ADB-2026-12-03",
        source="auditor",
        severity="material",
        description="Wrong release status",
        logged_at=NOW,
        story_rank=2,
    )
    append_resolution(
        log, refers_to="E0001", correction_ref="page note", description="Corrected", logged_at=NOW
    )


def test_phase1_report_all_pass(tmp_path: Path) -> None:
    make_editions(tmp_path / "editions")
    text = phase1_report(tmp_path / "editions")
    assert "Editions: PASS" in text and "complete (pass `validate --stage published`): 14" in text
    assert "H1 supply (should-pass): PASS" in text
    assert "H3 time (should-pass): PASS" in text and "median minutes per edition: 120" in text
    assert "H6 production stability (must-pass): PASS" in text
    assert "EXP private editions: 14" in text and "FR-M manual public editions: 0 / 30" in text


def test_phase1_report_detects_slow_and_unstable(tmp_path: Path) -> None:
    make_editions(tmp_path / "editions", minutes=170, manual_fix_days=(2, 9))
    text = phase1_report(tmp_path / "editions")
    assert "H3 time (should-pass): FAIL" in text
    assert "H6 production stability (must-pass): FAIL" in text
    assert "renders without a manual fix: 12/14 (need >= 13)" in text


def test_experiment_report_dry_run_computes_every_metric(tmp_path: Path) -> None:
    make_editions(tmp_path / "editions")
    make_experiment(tmp_path / "experiment")
    result = experiment_report(tmp_path / "experiment", tmp_path / "editions")
    text = result.text
    assert result.integrity_ok
    assert "H2 accuracy and provenance (must-pass a, b): PASS" in text
    assert "(c) material/critical errors in total, corrected or not: 1" in text
    assert "H4 usefulness (must-pass; early qualitative signal): PASS" in text
    assert "D1 mean: 4.00" in text and "response rate: 112/140 panel-days = 80%" in text
    assert "H5 distinctiveness and coverage (should-pass): PASS" in text
    assert "editions audited by the independent auditor: 11" in text
    assert "not evidence of product-market fit" in text


def test_low_response_rate_is_invalid_not_pass(tmp_path: Path) -> None:
    make_editions(tmp_path / "editions")
    make_experiment(tmp_path / "experiment", d1=5, responders=4)
    text = experiment_report(tmp_path / "experiment", tmp_path / "editions").text
    assert "H4 usefulness (must-pass; early qualitative signal): INVALID" in text


def test_tampered_error_log_is_refused(tmp_path: Path) -> None:
    make_editions(tmp_path / "editions")
    make_experiment(tmp_path / "experiment")
    log = tmp_path / "experiment" / "error-log.csv"
    with log.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    rows[1][COLUMNS.index("severity")] = "minor"
    write_csv(log, rows[0], rows[1:])
    result = experiment_report(tmp_path / "experiment", tmp_path / "editions")
    assert not result.integrity_ok and "REFUSED" in result.text
    cli = CliRunner().invoke(
        app,
        [
            "report",
            "experiment",
            "--experiment",
            str(tmp_path / "experiment"),
            "--editions",
            str(tmp_path / "editions"),
        ],
    )
    assert cli.exit_code == 1


def test_cli_reports_run(tmp_path: Path) -> None:
    make_editions(tmp_path / "editions")
    make_experiment(tmp_path / "experiment")
    runner = CliRunner()
    r1 = runner.invoke(app, ["report", "phase1", "--editions", str(tmp_path / "editions")])
    assert r1.exit_code == 0 and "H3 time" in r1.output
    r2 = runner.invoke(
        app,
        [
            "report",
            "experiment",
            "--experiment",
            str(tmp_path / "experiment"),
            "--editions",
            str(tmp_path / "editions"),
        ],
    )
    assert r2.exit_code == 0 and "H4 usefulness" in r2.output


def test_committed_templates_have_expected_headers() -> None:
    from tests.conftest import ROOT

    exp = ROOT / "experiment"
    assert (exp / "error-log.csv").read_text().strip() == ",".join(COLUMNS)
    assert (exp / "panel-responses.csv").read_text().startswith("date,panel_code,watched_full,D1")
    for name in ("panel-roster.csv", "audit-log.csv", "coverage-misses.csv", "daily-notes.md"):
        assert (exp / name).exists()
