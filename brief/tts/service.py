"""Narration for one edition (ADR-004): lexicon, cache, provider chain, licence and budget gates.

For each segment (hook, one per story, outro):
1. apply the pronunciation lexicon;
2. compute the cache key `sha256(provider|model|model_version|voice|lang|speed|lexicon|text)`
   and reuse the cached WAV on a hit (after re-checking its hash);
3. on a miss, try the providers in order. A provider without a commercial-use licence is
   refused. A paid provider runs only if the paid fallback is enabled **and**
   `Budget.check("tts", …)` passes, and its cost is recorded.
4. Every WAV is checked here, not trusted from the provider: PCM16 mono, >= 22.05 kHz,
   non-empty. The service computes the sha256 itself.

If every provider fails, `NarrationFailedError` is raised: that day's Reel is skipped and
the site publishes web-only (EDITORIAL_PIPELINE quiet-day policy). Never pad or fake audio.
"""

from __future__ import annotations

import hashlib
import json
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from brief.budget import IST, Budget, BudgetExceededError, UsageEntry
from brief.tts.base import NarrationAudio, TTSProvider, TTSProviderError, VoiceSpec
from brief.tts.config import TTSConfig
from brief.tts.lexicon import Lexicon, load_lexicon

MIN_SAMPLE_RATE = 22050


class NarrationFailedError(Exception):
    """No provider could narrate a segment. Skip the Reel; publish web-only."""


@dataclass(frozen=True)
class Segment:
    index: int
    text: str


def edition_segments(edition: Any) -> list[Segment]:
    """Hook (0), one segment per story in rank order (1..n), outro (n + 1)."""
    script = edition.script
    if script is None:
        raise NarrationFailedError("edition has no script (hook and outro)")
    segments = [Segment(0, script.hook)]
    for n, story in enumerate(sorted(edition.stories, key=lambda s: s.rank), start=1):
        if not story.narration:
            raise NarrationFailedError(f"story rank {story.rank} has no narration text")
        segments.append(Segment(n, story.narration))
    segments.append(Segment(len(segments), script.outro))
    return segments


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_wav(path: Path) -> tuple[int, float]:
    """(sample_rate, duration_s) of a valid narration WAV, else TTSProviderError."""
    try:
        with wave.open(str(path), "rb") as w:
            channels, width, rate, frames = (
                w.getnchannels(),
                w.getsampwidth(),
                w.getframerate(),
                w.getnframes(),
            )
    except (OSError, EOFError, wave.Error) as exc:
        raise TTSProviderError(f"{path.name}: not a readable WAV ({exc})") from exc
    if channels != 1 or width != 2:
        raise TTSProviderError(f"{path.name}: must be PCM16 mono, got {channels} ch x {width} B")
    if rate < MIN_SAMPLE_RATE:
        raise TTSProviderError(f"{path.name}: sample rate {rate} < {MIN_SAMPLE_RATE}")
    if frames == 0:
        raise TTSProviderError(f"{path.name}: no audio")
    return rate, frames / rate


def cache_key(voice: VoiceSpec, lexicon: Lexicon, spoken: str) -> str:
    parts = [
        voice.provider,
        voice.model,
        voice.model_version,
        voice.voice,
        voice.lang_code,
        f"{voice.speed:.3f}",
        lexicon.content_hash,
        spoken,
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


class NarrationService:
    def __init__(
        self,
        chain: Sequence[tuple[TTSProvider, VoiceSpec]],
        lexicon: Lexicon,
        cache_dir: Path,
        *,
        paid_enabled: bool = False,
        budget: Budget | None = None,
    ) -> None:
        if not chain:
            raise ValueError("at least one provider is required")
        self.chain = list(chain)
        self.lexicon = lexicon
        self.cache_dir = cache_dir
        self.paid_enabled = paid_enabled
        self.budget = budget
        self.failures: list[str] = []

    # -------------------------------------------------------------- cache
    def _cached(self, key: str, voice: VoiceSpec) -> NarrationAudio | None:
        wav, meta = self.cache_dir / f"{key}.wav", self.cache_dir / f"{key}.json"
        if not (wav.exists() and meta.exists()):
            return None
        info = json.loads(meta.read_text(encoding="utf-8"))
        if file_sha256(wav) != info.get("sha256"):
            return None  # damaged or replaced: synthesise again
        rate, duration = inspect_wav(wav)
        return NarrationAudio(wav, rate, duration, info["sha256"], voice, 0.0, cached=True)

    # -------------------------------------------------------------- gates
    def _gate(self, provider: TTSProvider, text: str) -> float:
        if not provider.licence().commercial_use_ok:
            raise TTSProviderError(f"{provider.name}: no commercial-use licence; refused")
        if not provider.is_paid:
            return 0.0
        if not self.paid_enabled:
            raise TTSProviderError(f"{provider.name}: paid TTS is disabled; refused")
        if self.budget is None:
            raise TTSProviderError(f"{provider.name}: paid TTS needs a budget check; refused")
        estimate = provider.estimate_cost_usd(text)
        try:
            self.budget.check("tts", estimate, provider=provider.name, operation="synthesize")
        except BudgetExceededError as exc:
            raise TTSProviderError(f"{provider.name}: {exc}") from exc
        return estimate

    # -------------------------------------------------------------- synthesis
    def narrate(self, segment: Segment) -> NarrationAudio:
        spoken = self.lexicon.apply(segment.text)
        for _provider, voice in self.chain:
            hit = self._cached(cache_key(voice, self.lexicon, spoken), voice)
            if hit is not None:
                return hit
        errors = []
        for provider, voice in self.chain:
            key = cache_key(voice, self.lexicon, spoken)
            try:
                self._gate(provider, spoken)
                return self._synthesize(provider, voice, key, spoken, segment)
            except TTSProviderError as exc:
                errors.append(str(exc))
                self.failures.append(f"segment {segment.index}: {exc}")
        raise NarrationFailedError(f"segment {segment.index}: " + "; ".join(errors))

    def _synthesize(
        self, provider: TTSProvider, voice: VoiceSpec, key: str, spoken: str, segment: Segment
    ) -> NarrationAudio:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_dir / f"{key}.partial.wav"
        try:
            result = provider.synthesize(spoken, voice, tmp)
            rate, duration = inspect_wav(tmp)
            digest = file_sha256(tmp)
        except TTSProviderError:
            tmp.unlink(missing_ok=True)
            raise
        except Exception as exc:  # an engine crash must not take the pipeline down
            tmp.unlink(missing_ok=True)
            raise TTSProviderError(f"{provider.name}: {type(exc).__name__}: {exc}") from exc
        final = self.cache_dir / f"{key}.wav"
        tmp.replace(final)
        meta = {
            "sha256": digest,
            "sample_rate": rate,
            "duration_s": round(duration, 3),
            "provider": voice.provider,
            "model": voice.model,
            "model_version": voice.model_version,
            "voice": voice.voice,
            "lexicon": self.lexicon.content_hash,
            "segment": segment.index,
            "text": spoken,
        }
        (self.cache_dir / f"{key}.json").write_text(json.dumps(meta, indent=2) + "\n")
        if provider.is_paid and self.budget is not None:
            self.budget.record(
                UsageEntry(
                    at=datetime.now(IST),
                    category="tts",
                    provider=provider.name,
                    operation="synthesize",
                    cost_usd=result.cost_usd,
                    model=voice.model,
                )
            )
        return NarrationAudio(final, rate, duration, digest, voice, result.cost_usd)

    def narrate_all(self, segments: Sequence[Segment]) -> list[NarrationAudio]:
        return [self.narrate(s) for s in segments]


def narration_refs(audio: Sequence[NarrationAudio]) -> list[dict[str, Any]]:
    """`media.narration[]` entries for the edition record (provenance, ADR-004)."""
    return [
        {
            "segment": n,
            "file": a.path.as_posix(),
            "sha256": a.sha256,
            "tts_provider": a.voice.provider,
            "tts_model": f"{a.voice.model}@{a.voice.model_version}",
            "voice": a.voice.voice,
        }
        for n, a in enumerate(audio)
    ]


ProviderFactory = Callable[[TTSConfig], TTSProvider]


def default_registry() -> dict[str, ProviderFactory]:
    from brief.tts.kokoro import KokoroProvider  # imported late: needs the `tts` extra

    return {"kokoro": KokoroProvider}


def build_service(
    cfg: TTSConfig,
    registry: dict[str, ProviderFactory] | None = None,
    budget: Budget | None = None,
) -> NarrationService:
    """The only place an engine is chosen: `engine` + `active_voice` in config/tts.yaml."""
    registry = registry if registry is not None else default_registry()
    if cfg.engine not in registry:
        raise NarrationFailedError(f"no provider registered for engine {cfg.engine!r}")
    provider = registry[cfg.engine](cfg)
    return NarrationService(
        [(provider, cfg.voice_spec())],
        load_lexicon(cfg.lexicon),
        cfg.cache_dir,
        paid_enabled=cfg.paid_fallback,
        budget=budget,
    )
