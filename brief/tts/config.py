"""Narration voice selection from `config/tts.yaml` (ADR-004).

The founder chose voice **C** (Kokoro `am_adam`) on 2026-11-11 without a listening test.
The voice can be switched to **B** (`af_heart`) or **D** (`bf_emma`) and nothing else in
the pipeline changes. Any other letter, a voice without a commercial-use licence record,
or an enabled paid fallback is refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

DEFAULT_TTS_CONFIG = Path("config/tts.yaml")
ALLOWED_VOICES = ("B", "C", "D")
DEVICES = ("cpu", "mps")
_ACTIVE_LINE = re.compile(r"^active_voice:\s*\S+", re.MULTILINE)


class TTSConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Voice:
    letter: str
    voice_id: str
    lang_code: str
    file: str
    sha256: str


@dataclass(frozen=True)
class TTSConfig:
    engine: str
    device: str
    paid_fallback: bool
    model_repo: str
    model_revision: str
    weights_sha256: str
    licence_record: str
    voices: dict[str, Voice]
    active: Voice


def _require(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise TTSConfigError(f"missing {key!r}")
    return raw[key]


def load_tts_config(path: Path = DEFAULT_TTS_CONFIG) -> TTSConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise TTSConfigError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TTSConfigError(f"{path}: expected a mapping")
    if _require(raw, "engine") != "kokoro":
        raise TTSConfigError("engine must be 'kokoro' (Piper is on hold; paid TTS disabled)")
    device = _require(raw, "device")
    if device not in DEVICES:
        raise TTSConfigError(f"device must be one of {DEVICES}")
    if _require(raw, "paid_fallback") is not False:
        raise TTSConfigError("paid_fallback must stay false (founder decision, ADR-004)")
    licence = _require(raw, "licence")
    if licence.get("commercial_use_ok") is not True or not licence.get("record"):
        raise TTSConfigError("a voice needs a commercial-use licence record (ADR-004)")
    voices_raw = _require(raw, "voices")
    if set(voices_raw) != set(ALLOWED_VOICES):
        raise TTSConfigError(f"voices must be exactly {ALLOWED_VOICES}, found {sorted(voices_raw)}")
    voices = {}
    for letter in ALLOWED_VOICES:
        v = voices_raw[letter]
        sha = str(v["sha256"])
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise TTSConfigError(f"voice {letter}: sha256 must be 64 hex characters")
        voices[letter] = Voice(letter, str(v["voice_id"]), str(v["lang_code"]), str(v["file"]), sha)
    active = str(_require(raw, "active_voice")).upper()
    if active not in ALLOWED_VOICES:
        raise TTSConfigError(f"active_voice must be one of {ALLOWED_VOICES}, not {active!r}")
    model = _require(raw, "model")
    return TTSConfig(
        engine="kokoro",
        device=device,
        paid_fallback=False,
        model_repo=str(model["repo"]),
        model_revision=str(model["revision"]),
        weights_sha256=str(model["weights_sha256"]),
        licence_record=str(licence["record"]),
        voices=voices,
        active=voices[active],
    )


def set_active_voice(letter: str, path: Path = DEFAULT_TTS_CONFIG) -> Voice:
    """Switch the narration voice, keeping the file's comments. Returns the new voice."""
    letter = letter.strip().upper()
    if letter not in ALLOWED_VOICES:
        raise TTSConfigError(f"voice must be one of {ALLOWED_VOICES}, not {letter!r}")
    load_tts_config(path)  # refuse to edit a config that is already invalid
    text = path.read_text(encoding="utf-8")
    if len(_ACTIVE_LINE.findall(text)) != 1:
        raise TTSConfigError(f"{path}: expected exactly one 'active_voice:' line")
    path.write_text(_ACTIVE_LINE.sub(f"active_voice: {letter}", text), encoding="utf-8")
    return load_tts_config(path).active
