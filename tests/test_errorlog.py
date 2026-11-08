"""P1-19: the error log is append-only and tamper-evident, anchored to a protected genesis."""

from __future__ import annotations

import csv
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brief.budget import IST
from brief.cli import app
from brief.experiment.errorlog import (
    COLUMNS,
    ErrorLogIntegrityError,
    add_checkpoint,
    anchor_path_for,
    append_error,
    append_resolution,
    full_verify,
    init_anchor,
    load_anchor,
    read_rows,
    summarize,
    verify,
)

NOW = datetime(2026, 12, 4, 9, 10, tzinfo=IST)


def make_log(directory: Path) -> Path:
    log = directory / "error-log.csv"
    init_anchor(log, NOW)
    append_error(log, issue_key="ADB-2026-12-03", source="auditor", severity="material",
                 description="Wrong release status", logged_at=NOW, story_rank=2,
                 evidence_url="https://example.com/x")  # fmt: skip
    append_error(log, issue_key="ADB-2026-12-03", source="self", severity="minor",
                 description="Typo in card", logged_at=NOW, story_rank=3)  # fmt: skip
    append_resolution(log, refers_to="E0001", correction_ref="corrections/2026-12-04",
                      description="Page corrected; note added", logged_at=NOW)  # fmt: skip
    return log


def rewrite(log: Path, rows: list[list[str]]) -> None:
    with log.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)


def raw(log: Path) -> list[list[str]]:
    with log.open(newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def problems_of(log: Path) -> list[str]:
    return verify(read_rows(log), load_anchor(log))


# ------------------------------------------------------------------ chain basics


def test_intact_log_verifies_and_summarises(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = read_rows(log)
    assert [r["entry_id"] for r in rows] == ["E0001", "E0002", "E0003"]
    assert problems_of(log) == []
    s = summarize(rows)
    assert (s.total_material_or_critical, s.unresolved_material_or_critical, s.minor) == (1, 0, 1)


def test_chain_starts_from_the_random_genesis(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    anchor = load_anchor(log)
    assert anchor is not None and anchor.genesis != "0" * 64
    assert read_rows(log)[0]["prev_hash"] == anchor.genesis


def test_every_append_records_a_checkpoint(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    anchor = load_anchor(log)
    assert anchor is not None
    assert [cp["count"] for cp in anchor.checkpoints] == [1, 2, 3]
    assert anchor.checkpoints[-1]["head_hash"] == read_rows(log)[-1]["row_hash"]


def test_corrected_error_still_counts(tmp_path: Path) -> None:
    s = summarize(read_rows(make_log(tmp_path)))
    assert s.total_material_or_critical == 1  # resolved, but never erased


def test_unresolved_error_is_reported(tmp_path: Path) -> None:
    log = tmp_path / "e.csv"
    init_anchor(log, NOW)
    append_error(log, issue_key="ADB-2026-12-05", source="panel", severity="critical",
                 description="Wrong model name", logged_at=NOW)  # fmt: skip
    assert summarize(read_rows(log)).unresolved_ids == ("E0001",)


# ------------------------------------------------------------------ tampering


def test_edited_row_is_detected(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = raw(log)
    rows[1][COLUMNS.index("severity")] = "minor"  # downgrade the material error
    rewrite(log, rows)
    assert any("edited" in p for p in problems_of(log))


def test_deleted_middle_row_is_detected(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = raw(log)
    del rows[1]
    rewrite(log, rows)
    assert problems_of(log)


def test_reordered_rows_are_detected(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = raw(log)
    rows[1], rows[2] = rows[2], rows[1]
    rewrite(log, rows)
    assert problems_of(log)


def test_truncated_tail_is_detected_by_checkpoint(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rewrite(log, raw(log)[:-1])  # cut the resolution row; the rest of the chain is valid
    assert any("truncated" in p for p in problems_of(log))


def test_log_rebuilt_from_a_different_genesis_is_detected(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    forged = forged_dir / "error-log.csv"
    init_anchor(forged, NOW)  # attacker's own chain, consistent with itself
    append_error(forged, issue_key="ADB-2026-12-03", source="self", severity="minor",
                 description="harmless", logged_at=NOW)  # fmt: skip
    shutil.copy(forged, log)  # replace the rows, keep the protected anchor
    assert any("genesis" in p for p in problems_of(log))


def test_append_refused_on_tampered_log(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    rows = raw(log)
    rows[2][COLUMNS.index("description")] = "changed"
    rewrite(log, rows)
    with pytest.raises(ErrorLogIntegrityError):
        append_error(log, issue_key="ADB-2026-12-06", source="self", severity="minor",
                     description="x", logged_at=NOW)  # fmt: skip


def test_anchor_required_and_never_recreated(tmp_path: Path) -> None:
    log = tmp_path / "e.csv"
    with pytest.raises(ErrorLogIntegrityError):
        append_error(log, issue_key="ADB-2026-12-06", source="self", severity="minor",
                     description="x", logged_at=NOW)  # fmt: skip
    init_anchor(log, NOW)
    with pytest.raises(ErrorLogIntegrityError, match="never be recreated"):
        init_anchor(log, NOW)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 - fixed test arguments
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com",  # noqa: S607
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        check=True, capture_output=True,
    )  # fmt: skip


def test_git_protects_the_anchor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    log = make_log(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "log")
    assert full_verify(log) == ([], [])

    # Attacker rewrites BOTH the log and the anchor consistently: chain alone looks fine.
    anchor_path_for(log).unlink()
    log.unlink()
    init_anchor(log, NOW)
    append_error(log, issue_key="ADB-2026-12-03", source="self", severity="minor",
                 description="harmless", logged_at=NOW)  # fmt: skip
    assert problems_of(log) == []
    problems, _ = full_verify(log)
    assert any("genesis differs from the committed" in p for p in problems)


def test_uncommitted_anchor_only_warns(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    log = make_log(repo)
    problems, warnings = full_verify(log)
    assert problems == [] and any("not committed" in w for w in warnings)


def test_manual_checkpoint_is_idempotent(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    assert add_checkpoint(log, NOW) is None  # already checkpointed by the appends


# ------------------------------------------------------------------ inputs and CLI


def test_input_validation(tmp_path: Path) -> None:
    log = tmp_path / "e.csv"
    init_anchor(log, NOW)
    with pytest.raises(ValueError, match="severity"):
        append_error(log, issue_key="ADB-2026-12-06", source="self", severity="bad",
                     description="x", logged_at=NOW)  # fmt: skip
    with pytest.raises(ValueError, match="timezone"):
        append_error(log, issue_key="ADB-2026-12-06", source="self", severity="minor",
                     description="x", logged_at=datetime(2026, 12, 4, 9, 10))  # fmt: skip
    with pytest.raises(ValueError, match="no error"):
        append_resolution(log, refers_to="E0009", correction_ref="c", description="d",
                          logged_at=NOW)  # fmt: skip


def test_cli_init_log_resolve_verify(tmp_path: Path) -> None:
    log = tmp_path / "error-log.csv"
    runner = CliRunner()
    assert runner.invoke(app, ["experiment", "init-log", "--log", str(log)]).exit_code == 0
    r1 = runner.invoke(app, ["experiment", "log-error", "--issue-key", "ADB-2026-12-03",
                             "--source", "auditor", "--severity", "material",
                             "--description", "Wrong date", "--story-rank", "1",
                             "--log", str(log)])  # fmt: skip
    assert r1.exit_code == 0 and "E0001" in r1.output
    r2 = runner.invoke(app, ["experiment", "resolve-error", "--refers-to", "E0001",
                             "--correction-ref", "page note", "--description", "Fixed",
                             "--log", str(log)])  # fmt: skip
    assert r2.exit_code == 0 and "E0002" in r2.output
    ok = runner.invoke(app, ["experiment", "verify-log", "--log", str(log)])
    assert ok.exit_code == 0 and "intact" in ok.output
    rewrite(log, raw(log)[:-1])
    bad = runner.invoke(app, ["experiment", "verify-log", "--log", str(log)])
    assert bad.exit_code == 1 and "truncated" in bad.output
