"""Narration voice selection from `config/tts.yaml` (ADR-004).

The founder chose voice **C** (Kokoro `am_adam`) on 2026-11-11 without a listening test.
The voice can be switched to **B** (`af_heart`) or **D** (`bf_emma`) and nothing else in
the pipeline changes. Any other letter, a voice without a commercial-use licence record,
or an enabled paid fallback is refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from brief.tts.base import LicenceRecord, VoiceSpec

DEFAULT_TTS_CONFIG = Path("config/tts.yaml")
ALLOWED_VOICES = ("B", "C", "D")
DEVICES = ("cpu", "mps")
_ACTIVE_LINE = re.compile(r"^active_voice:\s*\S+", re.MULTILINE)
_SHA = re.compile(r"[0-9a-f]{64}")


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
class ModelFiles:
    name: str
    repo: str
    revision: str
    weights_file: str
    weights_sha256: str
    config_file: str
    config_sha256: str


@dataclass(frozen=True)
class TTSConfig:
    engine: str
    device: str
    paid_fallback: bool
    speed: float
    lexicon: Path
    cache_dir: Path
    model: ModelFiles
    licence: LicenceRecord
    licence_record: str
    voices: dict[str, Voice]
    active: Voice

    def voice_spec(self) -> VoiceSpec:
        return VoiceSpec(
            provider=self.engine,
            model=self.model.name,
            model_version=f"{self.model.revision}:{self.model.weights_sha256[:16]}",
            voice=self.active.voice_id,
            lang_code=self.active.lang_code,
            speed=self.speed,
        )


def _require(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise TTSConfigError(f"missing {key!r}")
    return raw[key]


def _sha(value: Any, what: str) -> str:
    text = str(value)
    if not _SHA.fullmatch(text):
        raise TTSConfigError(f"{what}: sha256 must be 64 hex characters")
    return text


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
    lic = _require(raw, "licence")
    if lic.get("commercial_use_ok") is not True or not lic.get("record"):
        raise TTSConfigError("a voice needs a commercial-use licence record (ADR-004)")
    verified = lic.get("verified_on")
    if not isinstance(verified, date):
        raise TTSConfigError("licence.verified_on must be a date")
    licence = LicenceRecord(
        code_licence=str(lic["code"]),
        weights_licence=str(lic["weights"]),
        voice_data_licence=str(lic.get("voice_data", "")),
        commercial_use_ok=True,
        sources=tuple(str(s) for s in lic.get("sources", [])),
        verified_on=verified,
    )
    voices_raw = _require(raw, "voices")
    if set(voices_raw) != set(ALLOWED_VOICES):
        raise TTSConfigError(f"voices must be exactly {ALLOWED_VOICES}, found {sorted(voices_raw)}")
    voices = {
        letter: Voice(
            letter,
            str(v["voice_id"]),
            str(v["lang_code"]),
            str(v["file"]),
            _sha(v["sha256"], f"voice {letter}"),
        )
        for letter, v in ((k, voices_raw[k]) for k in ALLOWED_VOICES)
    }
    active = str(_require(raw, "active_voice")).upper()
    if active not in ALLOWED_VOICES:
        raise TTSConfigError(f"active_voice must be one of {ALLOWED_VOICES}, not {active!r}")
    speed = float(raw.get("speed", 1.0))
    if not 0.5 <= speed <= 2.0:
        raise TTSConfigError("speed must be between 0.5 and 2.0")
    m = _require(raw, "model")
    model = ModelFiles(
        name=str(m["name"]),
        repo=str(m["repo"]),
        revision=str(m["revision"]),
        weights_file=str(m["weights_file"]),
        weights_sha256=_sha(m["weights_sha256"], "model weights"),
        config_file=str(m["config_file"]),
        config_sha256=_sha(m["config_sha256"], "model config"),
    )
    return TTSConfig(
        engine="kokoro",
        device=device,
        paid_fallback=False,
        speed=speed,
        lexicon=Path(str(_require(raw, "lexicon"))),
        cache_dir=Path(str(_require(raw, "cache_dir"))),
        model=model,
        licence=licence,
        licence_record=str(lic["record"]),
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
