"""Final-output checks on the encoded MP4 (P1-10, ADR-015).

- 1080x1920, 30 fps, H.264 High, yuv420p; AAC at 48 kHz;
- duration 35-90 s; audio and video within 100 ms of each other;
- integrated loudness -14 +/- 1 LUFS and true peak <= -1.0 dBTP (ebur128 on the file);
- no clipped samples (decoded |x| >= 0.999).
`manifest` is the deterministic part of the probe: three renders of the same input must
give identical manifests.
"""

from __future__ import annotations

import json
import re
import subprocess
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LUFS_TARGET, LUFS_TOL = -14.0, 1.0
TRUE_PEAK_MAX = -1.0
CLIP_LEVEL = 0.999
DURATION_RANGE = (35.0, 90.0)
AV_DIFF_MAX = 0.100


@dataclass
class FinalChecks:
    manifest: dict[str, Any]
    integrated_lufs: float
    true_peak_dbtp: float
    clipped_samples: int
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "problems": self.problems,
            "integrated_lufs": self.integrated_lufs,
            "true_peak_dbtp": self.true_peak_dbtp,
            "clipped_samples": self.clipped_samples,
            "manifest": self.manifest,
        }


def _cmd(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, capture_output=True, check=True, timeout=600)  # noqa: S603


def probe_manifest(mp4: Path) -> dict[str, Any]:
    raw = json.loads(
        _cmd(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(mp4),
            ]
        ).stdout
    )
    manifest: dict[str, Any] = {"streams": []}
    for s in raw["streams"]:
        entry = {
            k: s.get(k)
            for k in ("codec_type", "codec_name", "profile", "width", "height", "pix_fmt",
                      "r_frame_rate", "sample_rate", "channels", "nb_frames", "duration")
        }  # fmt: skip
        manifest["streams"].append({k: v for k, v in entry.items() if v is not None})
    manifest["format_duration"] = raw["format"].get("duration")
    return manifest


def loudness(mp4: Path) -> tuple[float, float]:
    """(integrated LUFS, true peak dBTP) of the file's audio, via ebur128."""
    err = _cmd(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(mp4),
            "-map",
            "0:a:0",
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ]
    ).stderr.decode()
    summary = err[err.rfind("Summary:") :]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not (i and tp):
        raise ValueError("could not read ebur128 summary")
    return float(i.group(1)), float(tp.group(1))


def clipped_samples(mp4: Path) -> int:
    pcm = _cmd(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(mp4),
            "-map",
            "0:a:0",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-",
        ]
    ).stdout
    samples = array("f")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 4])
    return sum(1 for x in samples if x >= CLIP_LEVEL or x <= -CLIP_LEVEL)


def check_output(mp4: Path, expected: tuple[int, int, int] = (1080, 1920, 30)) -> FinalChecks:
    width, height, fps = expected
    manifest = probe_manifest(mp4)
    lufs, tp = loudness(mp4)
    clipped = clipped_samples(mp4)
    checks = FinalChecks(manifest, lufs, tp, clipped)
    video = [s for s in manifest["streams"] if s["codec_type"] == "video"]
    audio = [s for s in manifest["streams"] if s["codec_type"] == "audio"]
    p = checks.problems
    if len(video) != 1 or len(audio) != 1:
        p.append(f"expected 1 video + 1 audio stream, got {len(video)} + {len(audio)}")
        return checks
    v, a = video[0], audio[0]
    if (v.get("width"), v.get("height")) != (width, height):
        p.append(f"size {v.get('width')}x{v.get('height')}, expected {width}x{height}")
    if v.get("r_frame_rate") != f"{fps}/1":
        p.append(f"frame rate {v.get('r_frame_rate')}, expected {fps}/1")
    if v.get("codec_name") != "h264" or v.get("profile") != "High" or v.get("pix_fmt") != "yuv420p":
        p.append(f"video {v.get('codec_name')}/{v.get('profile')}/{v.get('pix_fmt')}, "
                 "expected h264/High/yuv420p")  # fmt: skip
    if a.get("codec_name") != "aac" or a.get("sample_rate") != "48000":
        p.append(f"audio {a.get('codec_name')} {a.get('sample_rate')} Hz, expected aac 48000")
    vd, ad = float(v.get("duration", 0)), float(a.get("duration", 0))
    if not DURATION_RANGE[0] <= vd <= DURATION_RANGE[1]:
        p.append(f"duration {vd:.2f} s outside {DURATION_RANGE[0]:.0f}-{DURATION_RANGE[1]:.0f} s")
    if abs(vd - ad) > AV_DIFF_MAX:
        p.append(f"audio/video differ by {abs(vd - ad) * 1000:.0f} ms (max 100)")
    if abs(lufs - LUFS_TARGET) > LUFS_TOL:
        p.append(f"loudness {lufs:.1f} LUFS, expected {LUFS_TARGET:.0f} +/- {LUFS_TOL:.0f}")
    if tp > TRUE_PEAK_MAX:
        p.append(f"true peak {tp:.1f} dBTP above {TRUE_PEAK_MAX}")
    if clipped:
        p.append(f"{clipped} clipped samples")
    return checks
