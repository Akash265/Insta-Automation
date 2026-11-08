"""Smoke tests for the `brief` CLI (P0-02, P0-03)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from brief import __version__, cli
from brief.doctor import CheckResult

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"brief {__version__}"


def test_help_lists_doctor() -> None:
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.output


def test_doctor_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_checks", lambda: [CheckResult("python", True, "3.12")])
    assert runner.invoke(cli.app, ["doctor"]).exit_code == 0

    monkeypatch.setattr(
        cli,
        "run_checks",
        lambda: [CheckResult("ffmpeg", False, "not found"), CheckResult("subs", False, "x", False)],
    )
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1
    assert "[FAIL] ffmpeg" in result.output


def test_optional_failure_does_not_fail_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_checks", lambda: [CheckResult("subs", False, "x", False)])
    assert runner.invoke(cli.app, ["doctor"]).exit_code == 0
