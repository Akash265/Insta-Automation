"""`brief render`: assemble the Reel from cards, narration and subtitles (P1-10, ADR-015).

Steps:
1. Join the narration segments (WAV, same rate) with a short pause after each, and keep
   the timeline: segment n starts at `starts[n]`.
2. Loudness: measure, pre-gain to about -14 LUFS with a peak limiter at 48 kHz, then
   two-pass `loudnorm` with `linear=true` (I -14 LUFS, TP -1.5 dBTP). See `normalise`.
3. Video, drawn by Pillow (not FFmpeg's zoompan, which moves in whole pixels and made
   the zoom stutter): each card gets a continuous sub-pixel push-in spread over its whole
   duration, the subtitle PNGs are composited in their time windows, and every card is
   encoded to H.264 High 30 fps in parallel. The pieces are joined without re-encoding
   and muxed with the AAC 48 kHz narration. The video is drawn once; a loudness retry
   only redoes the audio.
4. Final checks on the **encoded MP4** (`probe.py`). A failing render is never kept as
   the output. It is retried once with the true-peak target 0.5 dB lower; if that also
   fails, `RenderFailedError` is raised (no Reel that day; the site still publishes).
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import time
import wave
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from brief.media.cards import Card
from brief.media.probe import FinalChecks, check_output
from brief.media.subtitles import Chunk

FPS = 30
PAUSE_S = 0.4
TARGET_I = -14.0
TARGET_TP = -1.5
RETRY_TP_STEP = 0.5
ZOOM_TOTAL = 0.03  # push-in over each card's whole duration (never stops mid-card)
X264 = ["-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-threads", "2", "-r", str(FPS)]  # fmt: skip


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


def zoom_frame(card: Image.Image, index: int, count: int) -> Image.Image:
    """Card scaled about its centre by 1 + ZOOM_TOTAL * progress, with sub-pixel accuracy."""
    progress = index / (count - 1) if count > 1 else 0.0
    a = 1 / (1 + ZOOM_TOTAL * progress)
    cx, cy = card.width / 2, card.height / 2
    return card.transform(
        card.size,
        Image.Transform.AFFINE,
        (a, 0, cx * (1 - a), 0, a, cy * (1 - a)),
        resample=Image.Resampling.BILINEAR,
    )


def render_segment(
    card_path: str,
    count: int,
    first_frame: int,
    subs: list[tuple[int, int, str]],
    subtitle_top: int,
    out: str,
) -> str:
    """Encode one card's frames (zoom + subtitles) to H.264. Runs in a worker process.

    `subs` are (first frame, end frame, PNG path) in whole-video frame numbers.
    """
    card = Image.open(card_path).convert("RGB")
    overlays = [(a, b, Image.open(p).convert("RGBA")) for a, b, p in subs]
    proc = subprocess.Popen(  # noqa: S603 - fixed ffmpeg arguments, no shell
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",  # noqa: S607
         "-pix_fmt", "rgb24", "-s", f"{card.width}x{card.height}", "-r", str(FPS), "-i", "-",
         *X264, "-fflags", "+bitexact", "-map_metadata", "-1", out],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )  # fmt: skip
    if proc.stdin is None:
        raise RenderFailedError("could not open a pipe to ffmpeg")
    try:
        for i in range(count):
            frame = zoom_frame(card, i, count)
            n = first_frame + i
            for a, b, img in overlays:
                if a <= n < b:
                    frame.paste(img, (0, subtitle_top), img)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode() if proc.stderr else ""
    if proc.wait() != 0:
        raise RenderFailedError(f"encoding {Path(out).name} failed: {err.strip()[-400:]}")
    return out


def render_video(
    cards: Sequence[Card],
    frames: Sequence[int],
    subs: Sequence[tuple[Chunk, Path]],
    subtitle_top: int,
    work: Path,
) -> Path:
    """Silent H.264 video of all cards, segments encoded in parallel and joined losslessly."""
    starts = [0, *itertools.accumulate(frames)]
    jobs = []
    for n, (card, count) in enumerate(zip(cards, frames, strict=True)):
        lo, hi = starts[n], starts[n + 1]
        windows = []
        for chunk, png in subs:
            a, b = round(chunk.start * FPS), round(chunk.end * FPS)
            if a < hi and b > lo:
                windows.append((a, b, str(png)))
        jobs.append((str(card.path), count, lo, windows, subtitle_top,
                     str(work / f"segment-{n:02d}.mp4")))  # fmt: skip
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) // 2))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        parts = list(pool.map(render_segment, *zip(*jobs, strict=True)))
    listing = work / "segments.txt"
    listing.write_text("".join(f"file '{Path(p).name}'\n" for p in parts), encoding="utf-8")
    video = work / "video.mp4"
    _run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-f", "concat", "-safe", "0",
          "-i", str(listing), "-c", "copy", "-fflags", "+bitexact", "-map_metadata", "-1",
          str(video)])  # fmt: skip
    return video


def mux(video: Path, audio: Path, out: Path) -> None:
    _run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(video), "-i", str(audio),
          "-map", "0:v", "-map", "1:a", "-c:v", "copy",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
          "-movflags", "+faststart", "-shortest", "-fflags", "+bitexact",
          "-map_metadata", "-1", str(out)])  # fmt: skip


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
    video = render_video(cards, frames, subs, subtitle_top, work)
    mp4 = out_dir / f"{issue_key}.mp4"
    failures: list[str] = []
    for attempt, tp in enumerate((TARGET_TP, TARGET_TP - RETRY_TP_STEP), start=1):
        norm = work / "narration-48k.wav"
        loud = normalise(joined, norm, tp)
        candidate = work / f"attempt-{attempt}.mp4"
        mux(video, norm, candidate)
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
