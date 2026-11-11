"""P1-07 cards, P1-08 subtitles, P1-10 render (render tests need ffmpeg; no TTS engine)."""

from __future__ import annotations

import itertools
import json
import math
import os
import shutil
import struct
import wave
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat
from typer.testing import CliRunner

import brief.tts.service as service_mod
from brief.cli import app
from brief.edition.schema import Edition
from brief.media.cards import Card, CardOverflowError, render_cards, story_card
from brief.media.probe import check_output
from brief.media.render import RenderFailedError, render_reel, segment_frames, zoom_frame
from brief.media.subtitles import (
    Chunk,
    build_subtitles,
    chunk_text,
    line_fits,
    time_chunks,
)
from brief.media.theme import Theme, load_theme
from brief.tts.base import NarrationAudio, VoiceSpec
from brief.tts.config import TTSConfig
from tests.conftest import FIXTURES, ROOT
from tests.test_tts_service import FakeProvider

GOLDEN = ROOT / "tests" / "golden"
THEME = load_theme(ROOT / "video_templates" / "theme.yaml")
DIMS = (THEME.width, THEME.height, THEME.subtitle_top)
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def edition() -> Edition:
    return Edition.model_validate_json((FIXTURES / "normal.json").read_text(encoding="utf-8"))


def only_background(img: Image.Image, box: tuple[int, int, int, int], theme: Theme) -> bool:
    bg = theme.colours["background"][:3]
    colours = img.convert("RGB").crop(box).getcolors(maxcolors=1 << 22) or []
    return all(c == bg for _n, c in colours)


def outside_safe_area_is_background(img: Image.Image, theme: Theme) -> bool:
    s = theme.safe
    boxes = (
        (0, 0, theme.width, s.top),  # top bar
        (0, s.bottom, theme.width, theme.height),  # caption and buttons
        (0, 0, s.left, theme.height),  # left margin
        (s.right, 0, theme.width, theme.height),  # icon column
    )
    return all(only_background(img, box, theme) for box in boxes)


# ------------------------------------------------------------------ cards (P1-07)


def test_cards_match_golden_images(tmp_path: Path) -> None:
    cards = render_cards(THEME, edition(), tmp_path)
    assert [c.kind for c in cards] == ["intro"] + ["story"] * 5 + ["outro"]
    for card in (cards[0], cards[1], cards[-1]):
        golden = GOLDEN / card.path.name
        if os.environ.get("UPDATE_GOLDEN") == "1":
            GOLDEN.mkdir(exist_ok=True)
            shutil.copyfile(card.path, golden)
        diff = ImageChops.difference(
            Image.open(card.path).convert("RGB"), Image.open(golden).convert("RGB")
        )
        r, g, b = diff.split()
        peak = ImageChops.lighter(ImageChops.lighter(r, g), b)
        changed = peak.point(lambda v: 255 if v > 16 else 0).histogram()[255]
        assert changed < 0.001 * THEME.width * THEME.height, f"{card.path.name} changed"


def test_every_card_stays_inside_the_safe_area(tmp_path: Path) -> None:
    for card in render_cards(THEME, edition(), tmp_path):
        assert outside_safe_area_is_background(Image.open(card.path), THEME), card.path.name


def test_subtitle_band_is_left_empty_on_cards(tmp_path: Path) -> None:
    band = (0, THEME.subtitle_top, THEME.width, THEME.safe.bottom - 20)
    for card in render_cards(THEME, edition(), tmp_path):
        assert only_background(Image.open(card.path), band, THEME), card.path.name


def test_maximum_lengths_fit_without_overflow() -> None:
    story = (
        edition()
        .stories[0]
        .model_copy(
            update={
                "headline": "An unusually long headline about a model release that keeps "
                "going on to test the card at its limit",
                "card_text": ("Key phrase at the C09 card_text limit " * 3)[:90],
                "publisher": "A Publisher With A Rather Long Name Indeed",
            }
        )
    )
    assert story.card_text is not None and len(story.card_text) == 90
    img = story_card(THEME, story, 7, 7)
    assert outside_safe_area_is_background(img, THEME)


def test_text_that_cannot_fit_is_refused_not_cut() -> None:
    story = edition().stories[0].model_copy(update={"headline": "word " * 120})
    with pytest.raises(CardOverflowError):
        story_card(THEME, story, 1, 5)


# ------------------------------------------------------------------ subtitles (P1-08)


def test_chunks_respect_line_limits_and_safe_width() -> None:
    fits = line_fits(THEME)
    for story in edition().stories:
        text = story.narration or ""
        chunks = chunk_text(text, 42, 2, fits)
        assert " ".join(" ".join(c) for c in chunks) == " ".join(text.split())  # nothing lost
        for c in chunks:
            assert 1 <= len(c) <= 2 and all(len(line) <= 42 and fits(line) for line in c)
            assert sum(len(line) for line in c) >= 8, c  # no stray single words


def test_chunk_timing_is_contiguous_and_proportional() -> None:
    timed = time_chunks([("aaaa",), ("aaaaaaaa",), ("aaaa",)], start=10.0, duration=8.0)
    assert [(c.start, c.end) for c in timed] == [(10.0, 12.0), (12.0, 16.0), (16.0, 18.0)]


def test_subtitle_pngs_stay_in_the_band_and_safe_area(tmp_path: Path) -> None:
    text = edition().stories[3].narration or ""
    band_h = THEME.safe.bottom - THEME.subtitle_top
    for _chunk, path in build_subtitles(THEME, [(text, 0.0, 12.0)], tmp_path):
        img = Image.open(path)
        assert img.size == (THEME.width, band_h)
        left, _top, right, _bottom = img.getbbox() or (0, 0, 0, 0)
        assert THEME.safe.left <= left and right <= THEME.safe.right


# ------------------------------------------------------------------ render (P1-10)


def tone_wav(path: Path, seconds: float, amplitude: float, clip: bool = False) -> Path:
    rate = 24000
    frames = bytearray()
    for n in range(round(seconds * rate)):
        t = n / rate
        envelope = 0.55 + 0.45 * math.sin(2 * math.pi * 3 * t)  # syllable-like
        x = amplitude * envelope * math.sin(2 * math.pi * 220 * t)
        if clip:
            x = max(-1.0, min(1.0, 3 * x))
        frames += struct.pack("<h", max(-32767, min(32767, round(x * 32767))))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def render_inputs(
    tmp_path: Path, amplitude: float, clip: bool = False, seconds: float = 6.0
) -> tuple[list[Card], list[Path]]:
    cards = render_cards(THEME, edition(), tmp_path / "cards")
    wavs = [tone_wav(tmp_path / f"n{i}.wav", seconds, amplitude, clip) for i in range(len(cards))]
    return cards, wavs


def no_subs(_timeline: list[tuple[float, float]]) -> list[tuple[Chunk, Path]]:
    return []


def test_zoom_moves_smoothly_and_never_stops(tmp_path: Path) -> None:
    """Regression: zoompan moved in whole pixels (stutter) and stopped at its cap mid-card."""
    card = Image.open(render_cards(THEME, edition(), tmp_path)[1].path).convert("RGB")
    box = (90, 420, 990, 1120)  # headline area
    frames = [zoom_frame(card, i, 60).crop(box).convert("L") for i in range(0, 60, 3)]
    changes = [
        ImageStat.Stat(ImageChops.difference(a, b)).mean[0] for a, b in itertools.pairwise(frames)
    ]
    assert min(changes) > 0  # no frozen frames, right up to the end of the card
    assert max(changes) < 2.5 * (sum(changes) / len(changes))  # no jumps


def test_segment_frames_end_with_the_audio() -> None:
    frames = segment_frames([(0.0, 5.0), (5.4, 5.0), (10.8, 5.0)], 16.2)
    assert sum(frames) == round(16.2 * 30)


@needs_ffmpeg
def test_too_quiet_narration_is_normalised_and_renders_are_repeatable(tmp_path: Path) -> None:
    cards, wavs = render_inputs(tmp_path, amplitude=0.01)  # about -40 LUFS raw
    manifests = []
    for run in range(3):
        result = render_reel(cards, wavs, no_subs, tmp_path / f"r{run}", "ADB-TEST", DIMS)
        assert result.checks.passed, result.checks.problems
        manifests.append(result.checks.manifest)
    assert manifests[0] == manifests[1] == manifests[2]
    report = json.loads(result.report.read_text(encoding="utf-8"))
    assert report["checks"]["passed"] is True
    assert abs(report["checks"]["integrated_lufs"] + 14) <= 1


@needs_ffmpeg
def test_too_hot_clipping_narration_is_brought_under_the_peak_limit(tmp_path: Path) -> None:
    cards, wavs = render_inputs(tmp_path, amplitude=1.0, clip=True)
    c = render_reel(cards, wavs, no_subs, tmp_path / "out", "ADB-TEST", DIMS).checks
    assert c.passed and c.clipped_samples == 0 and c.true_peak_dbtp <= -1.0
    assert abs(c.integrated_lufs + 14) <= 1


@needs_ffmpeg
def test_failing_render_is_never_kept(tmp_path: Path) -> None:
    cards, wavs = render_inputs(tmp_path, amplitude=0.3, seconds=2.0)  # 7 x 2.4 s < 35 s
    with pytest.raises(RenderFailedError, match="duration"):
        render_reel(cards, wavs, no_subs, tmp_path / "out", "ADB-TEST", DIMS)
    assert not (tmp_path / "out" / "ADB-TEST.mp4").exists()


# ------------------------------------------------------------------ CLI


class ToneProvider(FakeProvider):
    def synthesize(self, text: str, voice: VoiceSpec, out: Path) -> NarrationAudio:
        self.calls.append(text)
        tone_wav(out, 6.0, 0.2)
        return NarrationAudio(out, 24000, 6.0, "ignored", voice, 0.0)


def test_cli_cards(tmp_path: Path) -> None:
    args = ["cards", str(FIXTURES / "normal.json"), "--out", str(tmp_path),
            "--theme", str(ROOT / "video_templates/theme.yaml")]  # fmt: skip
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0 and result.output.count(".png") == 7


@needs_ffmpeg
def test_cli_render_writes_media_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(cfg: TTSConfig) -> ToneProvider:
        return ToneProvider("kokoro")

    monkeypatch.setattr(service_mod, "default_registry", lambda: {"kokoro": factory})
    cfg = tmp_path / "tts.yaml"
    text = (ROOT / "config/tts.yaml").read_text(encoding="utf-8")
    text = text.replace("cache_dir: cache/tts", f"cache_dir: {tmp_path / 'cache'}")
    text = text.replace("lexicon: video_templates", f"lexicon: {ROOT / 'video_templates'}")
    cfg.write_text(text, encoding="utf-8")
    ed = tmp_path / "e.json"
    shutil.copy(FIXTURES / "normal.json", ed)
    result = CliRunner().invoke(app, [
        "render", str(ed), "--write", "--out", str(tmp_path / "out"), "--config", str(cfg),
        "--theme", str(ROOT / "video_templates/theme.yaml"),
    ])  # fmt: skip
    assert result.exit_code == 0, result.output
    data = Edition.model_validate_json(ed.read_text(encoding="utf-8"))
    assert data.media is not None and data.media.mp4 is not None and data.media.cover is not None
    assert data.media.mp4.key == "reels/ADB-2026-11-20.mp4" and len(data.media.narration) == 7
    assert check_output(tmp_path / "out" / "ADB-2026-11-20" / "ADB-2026-11-20.mp4").passed
