"""Provider-independent TTS interface (ADR-004).

The video pipeline never imports an engine: it only sees `NarrationAudio`. Changing engine
is a config change plus a benchmark, never a pipeline rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol


class TTSProviderError(Exception):
    """A provider could not produce audio (model missing, load failure, bad output)."""


@dataclass(frozen=True)
class VoiceSpec:
    provider: str  # "kokoro" | "<paid vendor>"
    model: str  # e.g. "Kokoro-82M"
    model_version: str  # pinned revision + weights hash, from config/tts.yaml
    voice: str  # e.g. "am_adam"
    lang_code: str = "a"
    speed: float = 1.0


@dataclass(frozen=True)
class LicenceRecord:  # required before a provider may be used
    code_licence: str
    weights_licence: str
    voice_data_licence: str
    commercial_use_ok: bool
    sources: tuple[str, ...]
    verified_on: date


@dataclass(frozen=True)
class NarrationAudio:  # the only thing render and subtitles consume
    path: Path  # WAV, PCM16 mono, the provider's native rate
    sample_rate: int
    duration_s: float
    sha256: str
    voice: VoiceSpec
    cost_usd: float  # 0.0 for local engines
    word_timings: tuple[tuple[str, float, float], ...] | None = None
    cached: bool = False


class TTSProvider(Protocol):
    name: str
    is_paid: bool

    def licence(self) -> LicenceRecord: ...

    def healthcheck(self) -> None:
        """Raise TTSProviderError unless the model is present, verified and loads offline."""

    def synthesize(self, text: str, voice: VoiceSpec, out: Path) -> NarrationAudio:
        """Write a WAV to `out`. The service re-checks the file; providers can't skip that."""

    def estimate_cost_usd(self, text: str) -> float: ...
