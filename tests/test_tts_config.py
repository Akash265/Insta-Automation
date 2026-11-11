"""Narration voice config: voice C by default, switchable only between B, C and D."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brief.cli import app
from brief.tts.config import TTSConfigError, load_tts_config, set_active_voice
from tests.conftest import ROOT

CONFIG = ROOT / "config" / "tts.yaml"


@pytest.fixture
def cfg(tmp_path: Path) -> Path:
    path = tmp_path / "tts.yaml"
    shutil.copy(CONFIG, path)
    return path


def test_committed_config_uses_voice_c_on_cpu_without_paid_fallback() -> None:
    c = load_tts_config(CONFIG)
    assert (c.active.letter, c.active.voice_id, c.active.lang_code) == ("C", "am_adam", "a")
    assert c.engine == "kokoro" and c.device == "cpu" and c.paid_fallback is False
    assert {k: v.voice_id for k, v in c.voices.items()} == {
        "B": "af_heart", "C": "am_adam", "D": "bf_emma",
    }  # fmt: skip


def test_hashes_match_the_benchmark_manifest() -> None:
    manifest = json.loads(
        (ROOT / "research/tts-benchmark/results/model-manifest.json").read_text(encoding="utf-8")
    )
    hashes = {f["file"]: f["sha256"] for f in manifest["files"]}
    c = load_tts_config(CONFIG)
    assert c.model.weights_sha256 == hashes["kokoro-v1_0.pth"]
    for v in c.voices.values():
        assert v.sha256 == hashes[v.file]


@pytest.mark.parametrize("letter", ["B", "d", "C"])
def test_switch_between_b_c_d_keeps_comments(cfg: Path, letter: str) -> None:
    assert set_active_voice(letter, cfg).letter == letter.upper()
    assert load_tts_config(cfg).active.letter == letter.upper()
    assert "# To change the voice" in cfg.read_text(encoding="utf-8")


@pytest.mark.parametrize("letter", ["A", "E", ""])
def test_other_voices_are_refused(cfg: Path, letter: str) -> None:
    with pytest.raises(TTSConfigError):
        set_active_voice(letter, cfg)
    assert load_tts_config(cfg).active.letter == "C"


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("paid_fallback: false", "paid_fallback: true", "paid_fallback"),
        ("engine: kokoro", "engine: piper", "engine"),
        ("commercial_use_ok: true", "commercial_use_ok: false", "licence"),
        ("active_voice: C", "active_voice: A", "active_voice"),
        ("device: cpu ", "device: cuda ", "device"),
    ],
)
def test_unsafe_configs_are_refused(cfg: Path, old: str, new: str, match: str) -> None:
    text = cfg.read_text(encoding="utf-8")
    assert old in text
    cfg.write_text(text.replace(old, new), encoding="utf-8")
    with pytest.raises(TTSConfigError, match=match):
        load_tts_config(cfg)


def test_cli_shows_and_switches(cfg: Path) -> None:
    runner = CliRunner()
    shown = runner.invoke(app, ["tts", "voice", "--config", str(cfg)])
    assert shown.exit_code == 0 and "active: C (am_adam)" in shown.output
    switched = runner.invoke(app, ["tts", "voice", "--set", "D", "--config", str(cfg)])
    assert switched.exit_code == 0 and "active: D (bf_emma)" in switched.output
    bad = runner.invoke(app, ["tts", "voice", "--set", "A", "--config", str(cfg)])
    assert bad.exit_code == 1
