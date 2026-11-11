"""Kokoro provider (ADR-004): local, offline, CPU by default.

Needs the optional extra: `uv sync --extra tts`. The model files come from the Hugging Face
cache at the revision pinned in `config/tts.yaml`, and every file is hash-checked before
use. Fetching them is a separate, explicit step (`brief tts fetch-model`); synthesis never
downloads anything.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from brief.tts.base import LicenceRecord, NarrationAudio, TTSProviderError, VoiceSpec
from brief.tts.config import TTSConfig
from brief.tts.service import file_sha256, inspect_wav


def _hub_path(cfg: TTSConfig, filename: str, *, download: bool) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise TTSProviderError("Kokoro is not installed: run `uv sync --extra tts`") from exc
    try:
        return Path(
            hf_hub_download(
                cfg.model.repo,
                filename,
                revision=cfg.model.revision,
                local_files_only=not download,
            )
        )
    except Exception as exc:
        hint = "" if download else " (run `uv run brief tts fetch-model` once)"
        raise TTSProviderError(f"model file {filename} unavailable{hint}: {exc}") from exc


def _expected_files(cfg: TTSConfig) -> dict[str, str]:
    files = {
        cfg.model.weights_file: cfg.model.weights_sha256,
        cfg.model.config_file: cfg.model.config_sha256,
    }
    files.update({v.file: v.sha256 for v in cfg.voices.values()})
    return files


def fetch_model(cfg: TTSConfig) -> dict[str, Path]:
    """Download (if needed) and hash-check the pinned files for all three voices."""
    paths = {}
    for name, sha in _expected_files(cfg).items():
        path = _hub_path(cfg, name, download=True)
        if file_sha256(path) != sha:
            raise TTSProviderError(f"{name}: sha256 does not match config/tts.yaml")
        paths[name] = path
    return paths


class KokoroProvider:
    name = "kokoro"
    is_paid = False

    def __init__(self, cfg: TTSConfig) -> None:
        self.cfg = cfg
        self._model: Any = None
        self._pipelines: dict[str, Any] = {}
        self._paths: dict[str, Path] = {}

    def licence(self) -> LicenceRecord:
        return self.cfg.licence

    def estimate_cost_usd(self, text: str) -> float:
        return 0.0

    def _verified(self, filename: str) -> Path:
        if filename not in self._paths:
            expected = _expected_files(self.cfg).get(filename)
            if expected is None:
                raise TTSProviderError(f"{filename} is not a configured model file")
            path = _hub_path(self.cfg, filename, download=False)
            if file_sha256(path) != expected:
                raise TTSProviderError(f"{filename}: sha256 does not match config/tts.yaml")
            self._paths[filename] = path
        return self._paths[filename]

    def _load(self, lang_code: str) -> Any:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # synthesis must never download
        if self.cfg.device == "mps":
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        try:
            from kokoro import KModel, KPipeline
        except ImportError as exc:
            raise TTSProviderError("Kokoro is not installed: run `uv sync --extra tts`") from exc
        if self._model is None:
            self._model = (
                KModel(
                    repo_id=self.cfg.model.repo,
                    config=str(self._verified(self.cfg.model.config_file)),
                    model=str(self._verified(self.cfg.model.weights_file)),
                )
                .to(self.cfg.device)
                .eval()
            )
        if lang_code not in self._pipelines:
            self._pipelines[lang_code] = KPipeline(
                lang_code=lang_code,
                repo_id=self.cfg.model.repo,
                model=self._model,
                device=self.cfg.device,
            )
        return self._pipelines[lang_code]

    def _voice_file(self, voice: VoiceSpec) -> Path:
        for v in self.cfg.voices.values():
            if v.voice_id == voice.voice:
                return self._verified(v.file)
        raise TTSProviderError(f"voice {voice.voice!r} is not one of the configured voices")

    def healthcheck(self) -> None:
        for name in _expected_files(self.cfg):
            self._verified(name)
        self._load(self.cfg.active.lang_code)

    def synthesize(self, text: str, voice: VoiceSpec, out: Path) -> NarrationAudio:
        import numpy as np
        import soundfile as sf

        pipeline = self._load(voice.lang_code)
        voice_path = str(self._voice_file(voice))
        chunks = [
            r.audio.detach().cpu().numpy()
            for r in pipeline(text, voice=voice_path, speed=voice.speed, split_pattern=r"\n+")
            if r.audio is not None
        ]
        if not chunks:
            raise TTSProviderError("Kokoro returned no audio")
        audio = np.clip(np.concatenate(chunks), -1.0, 1.0)
        sf.write(str(out), audio, 24000, subtype="PCM_16")
        rate, duration = inspect_wav(out)
        return NarrationAudio(out, rate, duration, file_sha256(out), voice, 0.0)
