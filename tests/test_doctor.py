"""Tests for `brief doctor` (P0-03). No real tools are invoked."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from brief.doctor import (
    CheckResult,
    check_ffmpeg,
    check_ffprobe,
    check_gitleaks,
    check_python,
    check_wrangler,
    render,
    run_checks,
)

FFMPEG_VERSION = "ffmpeg version 9.0.2 Copyright (c) 2000-2026 the FFmpeg developers\n"
ENCODERS_OK = " V....D libx264  libx264 H.264\n A....D aac  AAC (Advanced Audio Coding)\n"
FILTERS_OK = " .. ebur128  A->N  scanner\n .. loudnorm  A->A  normalization\n"


def fake_runner(table: dict[tuple[str, ...], str]) -> Callable[[Sequence[str]], str | None]:
    def run(args: Sequence[str]) -> str | None:
        return table.get(tuple(args))

    return run


def full_table(root: Path, wrangler_out: str = "4.152.0") -> dict[tuple[str, ...], str]:
    return {
        ("ffmpeg", "-hide_banner", "-version"): FFMPEG_VERSION,
        ("ffmpeg", "-hide_banner", "-encoders"): ENCODERS_OK,
        ("ffmpeg", "-hide_banner", "-filters"): FILTERS_OK,
        ("ffprobe", "-hide_banner", "-version"): "ffprobe version 9.0.2 Copyright\n",
        (str(root / "node_modules" / ".bin" / "wrangler"), "--version"): wrangler_out,
        ("gitleaks", "version"): "8.30.1\n",
    }


def write_package_json(root: Path, version: str = "4.152.0") -> None:
    (root / "package.json").write_text(json.dumps({"devDependencies": {"wrangler": version}}))


def test_python_version_gate() -> None:
    assert check_python((3, 12, 16)).ok
    assert not check_python((3, 9, 6)).ok


def test_ffmpeg_all_present_subtitles_missing_is_only_a_warning() -> None:
    results = {r.name: r for r in check_ffmpeg(fake_runner(full_table(Path("/x"))))}
    assert results["ffmpeg"].ok and results["ffmpeg"].detail == "9.0.2"
    assert results["ffmpeg encoders"].ok
    assert results["ffmpeg filters"].ok
    subs = results["ffmpeg subtitle filter"]
    assert not subs.ok and not subs.required


def test_ffmpeg_missing_encoder_fails() -> None:
    table = full_table(Path("/x"))
    table[("ffmpeg", "-hide_banner", "-encoders")] = " A....D aac  AAC\n"
    results = {r.name: r for r in check_ffmpeg(fake_runner(table))}
    assert not results["ffmpeg encoders"].ok
    assert "libx264" in results["ffmpeg encoders"].detail


def test_ffmpeg_absent() -> None:
    results = check_ffmpeg(fake_runner({}))
    assert len(results) == 1 and not results[0].ok and results[0].required


def test_ffprobe_and_gitleaks() -> None:
    table = full_table(Path("/x"))
    assert check_ffprobe(fake_runner(table)).detail == "9.0.2"
    assert check_gitleaks(fake_runner(table)).ok
    assert not check_gitleaks(fake_runner({})).ok


def test_wrangler_matches_pin(tmp_path: Path) -> None:
    write_package_json(tmp_path)
    assert check_wrangler(fake_runner(full_table(tmp_path)), tmp_path).ok


def test_wrangler_version_mismatch_fails(tmp_path: Path) -> None:
    write_package_json(tmp_path)
    result = check_wrangler(fake_runner(full_table(tmp_path, " wrangler 4.158.0")), tmp_path)
    assert not result.ok and "4.158.0" in result.detail


def test_wrangler_not_installed(tmp_path: Path) -> None:
    write_package_json(tmp_path)
    result = check_wrangler(fake_runner({}), tmp_path)
    assert not result.ok and "npm ci" in result.detail


def test_wrangler_no_pin(tmp_path: Path) -> None:
    assert not check_wrangler(fake_runner({}), tmp_path).ok


def test_run_checks_and_render(tmp_path: Path) -> None:
    write_package_json(tmp_path)
    results = run_checks(fake_runner(full_table(tmp_path)), tmp_path)
    assert all(r.ok for r in results if r.required)
    text = render(results)
    assert "[  ok] ffmpeg" in text
    assert "[warn] ffmpeg subtitle filter" in text


def test_render_marks_required_failure() -> None:
    text = render([CheckResult("x", False, "missing"), CheckResult("y", False, "opt", False)])
    assert "[FAIL] x" in text and "[warn] y" in text
