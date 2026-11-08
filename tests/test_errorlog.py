"""P1-19: the error log is append-only and tamper-evident."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brief.budget import IST
from brief.cli import app
from brief.experiment.errorlog import (
    COLUMNS,
    ErrorLogIntegrityError,
    append_error,
    append_resolution,
    read_rows,
    summarize,
    verify,
)

NOW = datetime(2026, 12, 4, 9, 10, tzinfo=IST)


def make_log(tmp_path: Path) -> Path:
    log = tmp_path / "error-log.csv"
    append_error(
        log,
        issue_key="ADB-2026-12-03",
        source="auditor",
        severity="material",
        description="Wrong release status",
        logged_at=NOW,
        story_rank=2,
        evidence_url="https://example.com/x",
    )
    append_error(
        log,
        issue_key="ADB-2026-12-03",
        source="self",
        severity="minor",
        description="Typo in card",
        logged_at=NOW,
        story_rank=3,
    )
    append_resolution(
        log,
        refers_to="E0001",
        correction_ref="corrections/2026-12-04",
        description="Page corrected; note added",
        logged_at=NOW,
    )
    return log


def rewrite(log: Path, rows: list[list[str]]) -> None:
    with log.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)


def raw(log: Path) -> list[list[str]]:
    with log.open(newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def test_intact_log_verifies_and_summarises(tmp_path: Path) -> None:
    rows = read_rows(make_log(tmp_path))
    assert [r["entry_id"] for r in rows] == ["E0001", "E0002", "E0003"]
    assert verify(rows) == []
    s = summarize(rows)
    assert (s.total_material_or_critical, s.unresolved_material_or_critical, s.minor) == (1, 0, 1)


def test_corrected_error_still_counts(tmp_path: Path) -> None:
    s = summarize(read_rows(make_log(tmp_path)))
    assert s.total_material_or_critical == 1  # resolved, but never erased


def test_unresolved_error_is_reported(tmp_path: Path) -> None:
    log = tmp_path / "e.csv"
    append_error(
        log,
        issue_key="ADB-2026-12-05",
        source="panel",
        severity="critical",
        description="Wrong model name",
        logged_at=NOW,
    )
    assert summarize(read_rows(log)).unresolved_ids == ("E0001",)


def test_edited_row_is_detected(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = raw(log)
    rows[1][COLUMNS.index("severity")] = "minor"  # downgrade the material error
    rewrite(log, rows)
    assert any("edited" in p for p in verify(read_rows(log)))


def test_deleted_row_is_detected(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = raw(log)
    del rows[1]  # drop the material error
    rewrite(log, rows)
    assert verify(read_rows(log))


def test_reordered_rows_are_detected(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = raw(log)
    rows[1], rows[2] = rows[2], rows[1]
    rewrite(log, rows)
    assert verify(read_rows(log))


def test_append_refused_on_tampered_log(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = raw(log)
    rows[2][COLUMNS.index("description")] = "changed"
    rewrite(log, rows)
    with pytest.raises(ErrorLogIntegrityError):
        append_error(
            log,
            issue_key="ADB-2026-12-06",
            source="self",
            severity="minor",
            description="x",
            logged_at=NOW,
        )


def test_input_validation(tmp_path: Path) -> None:
    log = tmp_path / "e.csv"
    with pytest.raises(ValueError, match="severity"):
        append_error(
            log,
            issue_key="ADB-2026-12-06",
            source="self",
            severity="bad",
            description="x",
            logged_at=NOW,
        )
    with pytest.raises(ValueError, match="timezone"):
        append_error(
            log,
            issue_key="ADB-2026-12-06",
            source="self",
            severity="minor",
            description="x",
            logged_at=datetime(2026, 12, 4, 9, 10),
        )
    with pytest.raises(ValueError, match="no error"):
        append_resolution(
            log, refers_to="E0009", correction_ref="c", description="d", logged_at=NOW
        )


def test_cli_log_and_resolve(tmp_path: Path) -> None:
    log = tmp_path / "error-log.csv"
    runner = CliRunner()
    r1 = runner.invoke(
        app,
        [
            "experiment",
            "log-error",
            "--issue-key",
            "ADB-2026-12-03",
            "--source",
            "auditor",
            "--severity",
            "material",
            "--description",
            "Wrong date",
            "--story-rank",
            "1",
            "--log",
            str(log),
        ],
    )
    assert r1.exit_code == 0 and "E0001" in r1.output
    r2 = runner.invoke(
        app,
        [
            "experiment",
            "resolve-error",
            "--refers-to",
            "E0001",
            "--correction-ref",
            "page note",
            "--description",
            "Fixed",
            "--log",
            str(log),
        ],
    )
    assert r2.exit_code == 0 and "E0002" in r2.output
    assert verify(read_rows(log)) == []
