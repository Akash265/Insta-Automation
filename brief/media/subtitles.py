"""Subtitles from segment durations (P1-08, ADR-015). No speech-to-text.

Method (decided 2026-11-11): each phrase chunk is drawn by Pillow as a transparent PNG
and overlaid by FFmpeg for its time window. The standard Homebrew FFmpeg has no
`subtitles`/`ass` filter, and this needs no extra dependency and stays deterministic.

Chunking: sentences are never merged; a long sentence is split into the fewest chunks
of similar length. Each chunk is at most 2 lines of at most 42 characters, and each
line also fits the safe area in pixels. Timing: a segment's spoken duration is shared
between its chunks in proportion to their characters. Subtitles show the editor's text,
not the lexicon respellings sent to the engine.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from brief.media.theme import Theme

PAD_X, PAD_Y, LINE_SPACING = 28, 18, 1.25


@dataclass(frozen=True)
class Chunk:
    start: float
    end: float
    lines: tuple[str, ...]


def _balanced(words: list[str], k: int) -> list[list[str]]:
    """Split words into k contiguous, non-empty groups of roughly equal characters."""
    sizes = [len(w) + 1 for w in words]
    total = sum(sizes)
    groups: list[list[str]] = []
    current: list[str] = []
    acc = 0
    for i, word in enumerate(words):
        current.append(word)
        acc += sizes[i]
        left = len(words) - i - 1
        needed = k - len(groups) - 1  # groups still to fill after this one
        if needed and left >= needed and (acc >= total * (len(groups) + 1) / k or left == needed):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _layout(
    words: list[str], max_chars: int, max_lines: int, fits: Callable[[str], bool]
) -> tuple[str, ...] | None:
    """Fewest balanced lines (<= max_lines) that each fit, or None."""
    for m in range(1, min(max_lines, len(words)) + 1):
        lines = [" ".join(g) for g in _balanced(words, m)]
        if all(len(line) <= max_chars and fits(line) for line in lines):
            return tuple(lines)
    return None


def chunk_text(
    text: str,
    max_chars: int = 42,
    max_lines: int = 2,
    fits: Callable[[str], bool] = lambda _line: True,
) -> list[tuple[str, ...]]:
    """Split narration into chunks of <= max_lines lines of <= max_chars.

    Chunks never cross a sentence end. A sentence that needs several chunks is split
    into the fewest chunks of similar length, so no word is left alone on screen.
    """
    chunks: list[tuple[str, ...]] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sentence.split()
        for k in range(1, len(words) + 1):
            laid = [_layout(g, max_chars, max_lines, fits) for g in _balanced(words, k)]
            if all(layout is not None for layout in laid):
                chunks.extend(layout for layout in laid if layout is not None)
                break
        else:
            raise ValueError(f"sentence can't be laid out as subtitles: {sentence[:60]!r}")
    return chunks


def time_chunks(chunks: list[tuple[str, ...]], start: float, duration: float) -> list[Chunk]:
    """Share `duration` between chunks by character count, back to back from `start`."""
    weights = [max(1, sum(len(line) for line in c)) for c in chunks]
    total = sum(weights)
    out, t = [], start
    for lines, w in zip(chunks, weights, strict=True):
        end = t + duration * w / total
        out.append(Chunk(round(t, 3), round(end, 3), lines))
        t = end
    if out:  # absorb rounding so the last chunk ends exactly with the speech
        last = out[-1]
        out[-1] = Chunk(last.start, round(start + duration, 3), last.lines)
    return out


def line_fits(theme: Theme) -> Callable[[str], bool]:
    font = theme.font("semibold", theme.subtitle_size)
    max_px = theme.safe.width - 2 * PAD_X
    return lambda line: font.getlength(line) <= max_px


def subtitle_box(theme: Theme, lines: tuple[str, ...]) -> tuple[int, int, int, int]:
    """Box of a chunk on the full canvas (left, top, right, bottom)."""
    font = theme.font("semibold", theme.subtitle_size)
    line_h = round(theme.subtitle_size * LINE_SPACING)
    width = max(round(font.getlength(line)) for line in lines) + 2 * PAD_X
    height = line_h * len(lines) + 2 * PAD_Y
    centre = (theme.safe.left + theme.safe.right) // 2
    left = centre - width // 2
    return (left, theme.subtitle_top, left + width, theme.subtitle_top + height)


def render_chunk(theme: Theme, lines: tuple[str, ...], path: Path) -> None:
    """Full-width transparent PNG of the subtitle band; overlay at y = subtitle_top."""
    band_h = theme.safe.bottom - theme.subtitle_top
    img = Image.new("RGBA", (theme.width, band_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = theme.font("semibold", theme.subtitle_size)
    line_h = round(theme.subtitle_size * LINE_SPACING)
    left, top, right, bottom = subtitle_box(theme, lines)
    top, bottom = top - theme.subtitle_top, bottom - theme.subtitle_top
    if bottom > band_h:
        raise ValueError("subtitle chunk is taller than the subtitle band")
    draw.rounded_rectangle(
        (left, top, right, bottom), radius=14, fill=theme.colours["subtitle_box"]
    )
    centre = (theme.safe.left + theme.safe.right) / 2
    for n, line in enumerate(lines):
        y = top + PAD_Y + n * line_h
        x = centre - font.getlength(line) / 2
        draw.text((x, y), line, font=font, fill=theme.colours["text"])
    img.save(path, format="PNG", optimize=False)


def build_subtitles(
    theme: Theme, segments: list[tuple[str, float, float]], out_dir: Path
) -> list[tuple[Chunk, Path]]:
    """segments: (display text, start s, spoken duration s). Returns chunks with PNGs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fits = line_fits(theme)
    result: list[tuple[Chunk, Path]] = []
    for text, start, duration in segments:
        raw = chunk_text(text, theme.subtitle_chars, theme.subtitle_lines, fits)
        for chunk in time_chunks(raw, start, duration):
            path = out_dir / f"sub-{len(result):03d}.png"
            render_chunk(theme, chunk.lines, path)
            result.append((chunk, path))
    return result
