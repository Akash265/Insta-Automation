"""`brief doctor`: verify the local toolchain (task P0-03).

Every check takes an injectable command runner so it can be tested without the
real tools installed. Commands are fixed argument lists (never shell strings).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 12)

Runner = Callable[[Sequence[str]], str | None]


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    required: bool = True


def run_command(args: Sequence[str]) -> str | None:
    """Run a fixed command and return its combined output, or None if it cannot run."""
    exe = args[0] if Path(args[0]).is_absolute() else shutil.which(args[0])
    if exe is None or not Path(exe).exists():
        return None
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [exe, *args[1:]], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout + proc.stderr


def check_python(version: tuple[int, int, int] | None = None) -> CheckResult:
    v = version or (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    text = ".".join(str(p) for p in v)
    return CheckResult("python", v[:2] >= MIN_PYTHON, f"{text} (need >= 3.12)")


def check_ffmpeg(runner: Runner) -> list[CheckResult]:
    out = runner(["ffmpeg", "-hide_banner", "-version"])
    if out is None:
        return [CheckResult("ffmpeg", False, "not found (brew install ffmpeg)")]
    match = re.search(r"ffmpeg version (\S+)", out)
    results = [CheckResult("ffmpeg", True, match.group(1) if match else "unknown version")]

    encoders = runner(["ffmpeg", "-hide_banner", "-encoders"]) or ""
    missing_enc = [e for e in ("libx264", "aac") if not re.search(rf"\s{e}\s", encoders)]
    results.append(
        CheckResult(
            "ffmpeg encoders",
            not missing_enc,
            "libx264, aac present" if not missing_enc else f"missing: {', '.join(missing_enc)}",
        )
    )

    filters = runner(["ffmpeg", "-hide_banner", "-filters"]) or ""
    missing_flt = [f for f in ("loudnorm", "ebur128") if not re.search(rf"\s{f}\s", filters)]
    results.append(
        CheckResult(
            "ffmpeg filters",
            not missing_flt,
            "loudnorm, ebur128 present"
            if not missing_flt
            else f"missing: {', '.join(missing_flt)}",
        )
    )

    has_subs = bool(re.search(r"\s(ass|subtitles)\s", filters))
    results.append(
        CheckResult(
            "ffmpeg subtitle filter",
            has_subs,
            "ass/subtitles present"
            if has_subs
            else "not in this build; subtitle method is decided in P1-08",
            required=False,
        )
    )
    return results


def check_ffprobe(runner: Runner) -> CheckResult:
    out = runner(["ffprobe", "-hide_banner", "-version"])
    if out is None:
        return CheckResult("ffprobe", False, "not found (installed with ffmpeg)")
    match = re.search(r"ffprobe version (\S+)", out)
    return CheckResult("ffprobe", True, match.group(1) if match else "unknown version")


def pinned_wrangler_version(root: Path = REPO_ROOT) -> str | None:
    try:
        data = json.loads((root / "package.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("devDependencies", {}).get("wrangler")
    return version if isinstance(version, str) else None


def check_wrangler(runner: Runner, root: Path = REPO_ROOT) -> CheckResult:
    pinned = pinned_wrangler_version(root)
    if pinned is None:
        return CheckResult("wrangler", False, "no pinned version in package.json")
    binary = root / "node_modules" / ".bin" / "wrangler"
    out = runner([str(binary), "--version"])
    if out is None:
        return CheckResult("wrangler", False, f"pinned {pinned} not installed (run `npm ci`)")
    match = re.search(r"(\d+\.\d+\.\d+)", out)
    found = match.group(1) if match else "unknown"
    return CheckResult("wrangler", found == pinned, f"{found} (pinned {pinned})")


def check_gitleaks(runner: Runner) -> CheckResult:
    out = runner(["gitleaks", "version"])
    if out is None:
        return CheckResult("gitleaks", False, "not found (brew install gitleaks)")
    return CheckResult("gitleaks", True, out.strip().splitlines()[0] if out.strip() else "present")


def run_checks(runner: Runner = run_command, root: Path = REPO_ROOT) -> list[CheckResult]:
    return [
        check_python(),
        *check_ffmpeg(runner),
        check_ffprobe(runner),
        check_wrangler(runner, root),
        check_gitleaks(runner),
    ]


def render(results: Sequence[CheckResult]) -> str:
    width = max(len(r.name) for r in results)
    lines = []
    for r in results:
        mark = "ok" if r.ok else ("FAIL" if r.required else "warn")
        lines.append(f"[{mark:>4}] {r.name:<{width}}  {r.detail}")
    return "\n".join(lines)
