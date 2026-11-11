"""`brief render`: assemble the Reel from cards, narration and subtitles (P1-10, ADR-015).

Steps:
1. Join the narration segments (WAV, same rate) with a short pause after each, and keep
   the timeline: segment n starts at `starts[n]`.
2. Loudness: measure, pre-gain to about -14 LUFS with a peak limiter at 48 kHz, then
   two-pass `loudnorm` with `linear=true` (I -14 LUFS, TP -1.5 dBTP). See `normalise`.
3. One FFmpeg run: each card is shown for its segment's frames with a slow zoom, the
   subtitle PNGs are overlaid in their time windows, and the result is encoded as
   H.264 High 30 fps + AAC 48 kHz.
4. Final checks on the **encoded MP4** (`probe.py`). A failing render is never kept as
   the output. It is retried once with the true-peak target 0.5 dB lower; if that also
   fails, `RenderFailedError` is raised (no Reel that day; the site still publishes).
"""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
import time
import wave
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brief.media.cards import Card
from brief.media.probe import FinalChecks, check_output
from brief.media.subtitles import Chunk

FPS = 30
PAUSE_S = 0.4
TARGET_I = -14.0
TARGET_TP = -1.5
RETRY_TP_STEP = 0.5
ZOOM_PER_FRAME = 0.0002  # slow push-in, max 4%
ZOOM_MAX = 1.04


class RenderFailedError(Exception):
    """The Reel could not be rendered to spec. Skip the Reel; publish web-only."""


@dataclass
class RenderResult:
    mp4: Path
    cover: Path
    checks: FinalChecks
    attempts: int
    seconds: float
    loudnorm: dict[str, Any]
    report: Path
    timeline: list[tuple[float, float]] = field(default_factory=list)


def _run(args: Sequence[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 - fixed ffmpeg arguments, no shell
            list(args), capture_output=True, text=True, check=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise RenderFailedError("ffmpeg is not installed") from exc
    except subprocess.CalledProcessError as exc:
        tail = "\n".join(exc.stderr.strip().splitlines()[-8:])
        raise RenderFailedError(f"{Path(args[0]).name} failed:\n{tail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderFailedError(f"{Path(args[0]).name} timed out") from exc


def join_narration(
    wavs: Sequence[Path], out: Path, pause_s: float = PAUSE_S
) -> list[tuple[float, float]]:
    """Concatenate WAVs with a pause after each. Returns (start, spoken duration) per segment."""
    params = None
    timeline: list[tuple[float, float]] = []
    frames_written = 0
    with wave.open(str(out), "wb") as dst:
        for path in wavs:
            with wave.open(str(path), "rb") as src:
                p = (src.getnchannels(), src.getsampwidth(), src.getframerate())
                if params is None:
                    params = p
                    dst.setnchannels(p[0])
                    dst.setsampwidth(p[1])
                    dst.setframerate(p[2])
                elif p != params:
                    raise RenderFailedError(f"{path.name}: audio format differs from segment 0")
                frames = src.readframes(src.getnframes())
            rate = params[2]
            n = len(frames) // (params[0] * params[1])
            timeline.append((frames_written / rate, n / rate))
            silence = b"\x00" * (round(pause_s * rate) * params[0] * params[1])
            dst.writeframes(frames + silence)
            frames_written += n + round(pause_s * rate)
    return timeline


def _loudnorm_measure(src: Path, tp: float) -> dict[str, Any]:
    proc = _run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af",
         f"loudnorm=I={TARGET_I}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"]
    )  # fmt: skip
    text = proc.stderr
    start = text.rfind("{")
    try:
        return dict(json.loads(text[start : text.rfind("}") + 1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise RenderFailedError("could not read loudnorm measurements") from exc


PRE_LIMIT = 0.794  # -2 dBFS sample-peak ceiling after the pre-gain, at 48 kHz
PRE_ATTACK_MS, PRE_RELEASE_MS = 1, 30  # fast: catches transients, costs little loudness
PRE_ITERATIONS = 4
PRE_STEP = 1.5  # limiting eats part of each gain increase, so overshoot the correction


def normalise(src: Path, out: Path, tp: float) -> dict[str, Any]:
    """Pre-gain + peak limiter, then two-pass linear loudnorm. Returns all measurements.

    Raw Kokoro narration has a peak-to-loudness ratio of about 20 dB. Reaching -14 LUFS
    with a constant gain would push its transient peaks above the true-peak target, so
    loudnorm would fall back to dynamic mode, which undershoots (measured -16 LUFS on the
    fixture). So first the track is brought near the target and its brief peaks are
    limited at 48 kHz, raising the gain by 1.5x the measured shortfall (up to 4 rounds) until
    it sits within 0.3 LU of -14. The two-pass linear loudnorm then only makes a small,
    constant correction.
    """
    first = _loudnorm_measure(src, tp)
    gain = TARGET_I - float(first["input_i"])
    staged = out.with_name(out.stem + "-limited.wav")
    steps = []
    for _ in range(PRE_ITERATIONS):
        _run(
            ["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(src), "-af",
             f"aresample=48000,volume={gain:.2f}dB,"
             f"alimiter=limit={PRE_LIMIT}:attack={PRE_ATTACK_MS}:release={PRE_RELEASE_MS}"
             ":level=false:latency=true",
             "-ac", "1", "-c:a", "pcm_s16le", str(staged)]
        )  # fmt: skip
        level = float(_loudnorm_measure(staged, tp)["input_i"])
        steps.append({"gain_db": round(gain, 2), "lufs": level})
        if abs(level - TARGET_I) <= 0.3:
            break
        gain += PRE_STEP * (TARGET_I - level)
    m = _loudnorm_measure(staged, tp)
    proc = _run(
        ["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(staged), "-af",
         f"loudnorm=I={TARGET_I}:TP={tp}:LRA=11:measured_I={m['input_i']}"
         f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
         f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
         ":linear=true:print_format=json,aresample=48000",
         "-ac", "1", "-c:a", "pcm_s16le", str(out)]
    )  # fmt: skip
    text = proc.stderr
    second = json.loads(text[text.rfind("{") : text.rfind("}") + 1])
    return {
        "target_tp": tp,
        "raw": first,
        "pre_gain_steps": steps,
        "measured": m,
        "applied": second,
        "linear": second.get("normalization_type") == "linear",
    }


def _video_args(
    cards: Sequence[Card],
    frames: Sequence[int],
    subs: Sequence[tuple[Chunk, Path]],
    audio: Path,
    out: Path,
    subtitle_top: int,
    width: int,
    height: int,
) -> list[str]:
    args = ["ffmpeg", "-hide_banner", "-nostats", "-y"]
    for card in cards:
        args += ["-i", str(card.path)]
    for _chunk, png in subs:
        args += ["-i", str(png)]
    args += ["-i", str(audio)]
    graph = []
    for n, count in enumerate(frames):
        graph.append(
            f"[{n}:v]scale={width}:{height},setsar=1,"
            f"zoompan=z='min(1+{ZOOM_PER_FRAME}*on,{ZOOM_MAX})':d={count}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={FPS},"
            f"trim=end_frame={count},setpts=PTS-STARTPTS[c{n}]"
        )
    graph.append(
        "".join(f"[c{n}]" for n in range(len(cards))) + f"concat=n={len(cards)}:v=1:a=0[v0]"
    )
    last = "v0"
    for i, (chunk, _png) in enumerate(subs):
        idx = len(cards) + i
        graph.append(
            f"[{last}][{idx}:v]overlay=0:{subtitle_top}:"
            f"enable='between(t,{chunk.start:.3f},{chunk.end:.3f})'[v{i + 1}]"
        )
        last = f"v{i + 1}"
    graph.append(f"[{last}]format=yuv420p[vout]")
    audio_idx = len(cards) + len(subs)
    args += [
        "-filter_complex", ";".join(graph),
        "-map", "[vout]", "-map", f"{audio_idx}:a",
        "-r", str(FPS), "-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
        "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "4",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", "-fflags", "+bitexact",
        "-map_metadata", "-1", str(out),
    ]  # fmt: skip
    return args


def segment_frames(timeline: Sequence[tuple[float, float]], total_s: float) -> list[int]:
    """Frames per card so that the video ends with the audio (no drift)."""
    bounds = [round(start * FPS) for start, _ in timeline] + [round(total_s * FPS)]
    return [b - a for a, b in itertools.pairwise(bounds)]


def render_reel(
    cards: Sequence[Card],
    narration: Sequence[Path],
    subtitles_for: Any,
    out_dir: Path,
    issue_key: str,
    theme_dims: tuple[int, int, int],
) -> RenderResult:
    """Render `out_dir/<issue_key>.mp4`. `subtitles_for(timeline)` builds the subtitle PNGs."""
    if len(cards) != len(narration):
        raise RenderFailedError(f"{len(cards)} cards but {len(narration)} narration segments")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RenderFailedError("ffmpeg/ffprobe not found on PATH")
    width, height, subtitle_top = theme_dims
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    joined = work / "narration-joined.wav"
    timeline = join_narration(narration, joined)
    with wave.open(str(joined), "rb") as w:
        total_s = w.getnframes() / w.getframerate()
    frames = segment_frames(timeline, total_s)
    subs = subtitles_for(timeline)
    mp4 = out_dir / f"{issue_key}.mp4"
    failures: list[str] = []
    for attempt, tp in enumerate((TARGET_TP, TARGET_TP - RETRY_TP_STEP), start=1):
        norm = work / "narration-48k.wav"
        loud = normalise(joined, norm, tp)
        candidate = work / f"attempt-{attempt}.mp4"
        _run(_video_args(cards, frames, subs, norm, candidate, subtitle_top, width, height))
        checks = check_output(candidate, expected=(width, height, FPS))
        if checks.passed:
            candidate.replace(mp4)
            cover = out_dir / f"{issue_key}-cover.png"
            shutil.copyfile(cards[0].path, cover)
            seconds = round(time.monotonic() - began, 1)
            report = out_dir / f"{issue_key}-render-report.json"
            report.write_text(json.dumps({
                "issue_key": issue_key, "attempts": attempt, "render_seconds": seconds,
                "loudnorm": loud, "checks": checks.as_dict(), "failures": failures,
                "segments": [{"start": s, "spoken": d, "frames": f}
                             for (s, d), f in zip(timeline, frames, strict=True)],
            }, indent=2) + "\n", encoding="utf-8")  # fmt: skip
            return RenderResult(mp4, cover, checks, attempt, seconds, loud, report, timeline)
        failures.append(f"attempt {attempt} (TP {tp}): " + "; ".join(checks.problems))
    raise RenderFailedError("render failed the final checks: " + " | ".join(failures))
