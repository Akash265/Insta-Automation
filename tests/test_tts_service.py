"""P1-06: narration service with a fake provider (no engine, no model, no network)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import wave
from datetime import date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

import brief.tts.service as service_mod
from brief.budget import IST, Budget, UsageEntry, load_config
from brief.cli import app
from brief.edition.schema import Edition
from brief.tts.base import LicenceRecord, NarrationAudio, TTSProviderError, VoiceSpec
from brief.tts.config import TTSConfig, load_tts_config, set_active_voice
from brief.tts.lexicon import Lexicon, LexiconError, load_lexicon
from brief.tts.service import (
    NarrationFailedError,
    NarrationService,
    Segment,
    build_service,
    edition_segments,
    narration_refs,
)
from tests.conftest import FIXTURES, ROOT

OK_LICENCE = LicenceRecord("Apache-2.0", "Apache-2.0", "permissive", True, (), date(2026, 11, 8))
VOICE = VoiceSpec("fake", "fake-model", "rev1", "am_adam")
LEXICON = Lexicon((("CUDA", "Kooda"),), "lexhash")


def write_wav(out: Path, *, rate: int = 24000, channels: int = 1, frames: int = 2400) -> None:
    with wave.open(str(out), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * frames * channels)


class FakeProvider:
    def __init__(
        self,
        name: str = "fake",
        *,
        paid: bool = False,
        licence_ok: bool = True,
        fail: Exception | None = None,
        rate: int = 24000,
        channels: int = 1,
    ) -> None:
        self.name, self.is_paid, self.fail = name, paid, fail
        self.rate, self.channels = rate, channels
        self._licence = dataclasses.replace(OK_LICENCE, commercial_use_ok=licence_ok)
        self.calls: list[str] = []

    def licence(self) -> LicenceRecord:
        return self._licence

    def healthcheck(self) -> None:
        pass

    def estimate_cost_usd(self, text: str) -> float:
        return 0.5 if self.is_paid else 0.0

    def synthesize(self, text: str, voice: VoiceSpec, out: Path) -> NarrationAudio:
        self.calls.append(text)
        if self.fail is not None:
            raise self.fail
        write_wav(out, rate=self.rate, channels=self.channels)
        return NarrationAudio(out, self.rate, 0.1, "ignored", voice, self.estimate_cost_usd(text))


def make_budget(directory: Path) -> Budget:
    directory.mkdir(parents=True, exist_ok=True)
    config = dataclasses.replace(load_config(ROOT / "config/budget_periods.yaml"), day1=None)
    cash = directory / "cash.csv"
    cash.write_text("date,category,item,amount_inr,note\n", encoding="utf-8")
    return Budget(config, directory / "usage.jsonl", cash)


def svc(tmp_path: Path, *providers: FakeProvider, **kw: object) -> NarrationService:
    chain = [(p, VOICE) for p in providers]
    return NarrationService(chain, LEXICON, tmp_path / "c", **kw)  # type: ignore[arg-type]


# ------------------------------------------------------------------ segments and contract


def test_edition_segments_are_hook_stories_outro() -> None:
    edition = Edition.model_validate_json((FIXTURES / "normal.json").read_text(encoding="utf-8"))
    assert edition.script is not None
    segs = edition_segments(edition)
    assert segs[0].text == edition.script.hook and segs[-1].text == edition.script.outro
    assert [s.index for s in segs] == list(range(len(edition.stories) + 2))


def test_output_contract_is_checked_by_the_service(tmp_path: Path) -> None:
    audio = svc(tmp_path, FakeProvider()).narrate(Segment(0, "Hello"))
    assert audio.path.suffix == ".wav" and audio.sample_rate == 24000
    assert audio.duration_s == pytest.approx(0.1)
    assert audio.sha256 == service_mod.file_sha256(audio.path)  # computed, not trusted
    assert audio.cost_usd == 0.0


@pytest.mark.parametrize(("rate", "channels"), [(16000, 1), (24000, 2)])
def test_bad_audio_is_refused_and_not_cached(tmp_path: Path, rate: int, channels: int) -> None:
    s = svc(tmp_path, FakeProvider(rate=rate, channels=channels))
    with pytest.raises(NarrationFailedError):
        s.narrate(Segment(0, "Hello"))
    assert not list((tmp_path / "c").glob("*.wav"))


# ------------------------------------------------------------------ cache


def test_unchanged_text_makes_zero_synthesis_calls(tmp_path: Path) -> None:
    p = FakeProvider()
    first = svc(tmp_path, p).narrate_all([Segment(0, "Hello"), Segment(1, "World")])
    again = svc(tmp_path, p).narrate_all([Segment(0, "Hello"), Segment(1, "World")])
    assert len(p.calls) == 2 and all(a.cached for a in again)
    assert [a.sha256 for a in again] == [a.sha256 for a in first]


def test_lexicon_voice_or_text_change_resynthesises(tmp_path: Path) -> None:
    p = FakeProvider()
    svc(tmp_path, p).narrate(Segment(0, "Runs on CUDA"))
    assert p.calls == ["Runs on Kooda"]
    other_lex = Lexicon((("CUDA", "Koo-da"),), "lexhash2")
    NarrationService([(p, VOICE)], other_lex, tmp_path / "c").narrate(Segment(0, "Runs on CUDA"))
    other_voice = dataclasses.replace(VOICE, voice="bf_emma")
    NarrationService([(p, other_voice)], LEXICON, tmp_path / "c").narrate(
        Segment(0, "Runs on CUDA")
    )
    assert len(p.calls) == 3


def test_damaged_cache_is_not_reused(tmp_path: Path) -> None:
    p = FakeProvider()
    audio = svc(tmp_path, p).narrate(Segment(0, "Hello"))
    audio.path.write_bytes(b"garbage")
    assert not svc(tmp_path, p).narrate(Segment(0, "Hello")).cached
    assert len(p.calls) == 2


# ------------------------------------------------------------------ gates and chain


def test_provider_without_commercial_licence_is_refused(tmp_path: Path) -> None:
    p = FakeProvider(licence_ok=False)
    with pytest.raises(NarrationFailedError, match="commercial-use"):
        svc(tmp_path, p).narrate(Segment(0, "Hello"))
    assert p.calls == []


def test_paid_provider_refused_unless_enabled_and_within_budget(tmp_path: Path) -> None:
    paid = FakeProvider("vendor", paid=True)
    with pytest.raises(NarrationFailedError, match="disabled"):
        svc(tmp_path, paid).narrate(Segment(0, "a"))
    spent = make_budget(tmp_path / "spent")
    spent.record(UsageEntry(datetime.now(IST), "tts", "vendor", "synthesize", 8.0))  # cap used
    with pytest.raises(NarrationFailedError, match="cap"):
        svc(tmp_path, paid, paid_enabled=True, budget=spent).narrate(Segment(0, "b"))
    assert paid.calls == []
    fresh = make_budget(tmp_path / "fresh")
    audio = svc(tmp_path, paid, paid_enabled=True, budget=fresh).narrate(Segment(0, "c"))
    assert audio.cost_usd == 0.5
    assert [e.cost_usd for e in fresh.usage() if e.status == "ok"] == [0.5]


def test_chain_falls_through_on_failure_and_crash(tmp_path: Path) -> None:
    broken = FakeProvider("broken", fail=RuntimeError("engine crashed"))
    backup = FakeProvider("backup")
    audio = svc(tmp_path, broken, backup).narrate(Segment(0, "Hello"))
    assert backup.calls == ["Hello"] and audio.path.exists()


def test_all_providers_failing_means_web_only(tmp_path: Path) -> None:
    s = svc(tmp_path, FakeProvider(fail=TTSProviderError("model missing")))
    with pytest.raises(NarrationFailedError, match="model missing"):
        s.narrate(Segment(3, "Hello"))


# ------------------------------------------------------------------ config wiring


@pytest.fixture
def cfg_path(tmp_path: Path) -> Path:
    path = tmp_path / "tts.yaml"
    text = (ROOT / "config/tts.yaml").read_text(encoding="utf-8")
    text = text.replace("cache_dir: cache/tts", f"cache_dir: {tmp_path / 'cache'}")
    text = text.replace("lexicon: video_templates", f"lexicon: {ROOT / 'video_templates'}")
    path.write_text(text, encoding="utf-8")
    return path


def fake_registry(made: list[FakeProvider]) -> dict[str, service_mod.ProviderFactory]:
    def factory(cfg: TTSConfig) -> FakeProvider:
        made.append(FakeProvider("kokoro"))
        return made[-1]

    return {"kokoro": factory}


def test_switching_voice_in_config_needs_no_pipeline_change(cfg_path: Path) -> None:
    made: list[FakeProvider] = []
    a = build_service(load_tts_config(cfg_path), fake_registry(made)).narrate(Segment(0, "Hi"))
    set_active_voice("D", cfg_path)
    b = build_service(load_tts_config(cfg_path), fake_registry(made)).narrate(Segment(0, "Hi"))
    assert (a.voice.voice, b.voice.voice) == ("am_adam", "bf_emma")
    assert (a.voice.lang_code, b.voice.lang_code) == ("a", "b")
    assert a.path != b.path


def test_unregistered_engine_is_refused(cfg_path: Path) -> None:
    with pytest.raises(NarrationFailedError, match="no provider"):
        build_service(load_tts_config(cfg_path), {})


def test_narration_refs_fit_the_edition_schema(tmp_path: Path) -> None:
    audio = svc(tmp_path, FakeProvider()).narrate_all([Segment(0, "a"), Segment(1, "b")])
    data = json.loads((FIXTURES / "normal.json").read_text(encoding="utf-8"))
    data["media"]["narration"] = narration_refs(audio)
    Edition.model_validate(data)


# ------------------------------------------------------------------ lexicon


def test_committed_lexicon_fixes_cuda_and_qwen_whole_words_only() -> None:
    lex = load_lexicon(ROOT / "video_templates/lexicon.yaml")
    out = lex.apply("CUDA's speed, Qwen-like names, CUDAX and Qwen.")
    assert out == "Kooda's speed, Qwen-like names, CUDAX and Kwen."


def test_lexicon_rejects_bad_entries(tmp_path: Path) -> None:
    bad = tmp_path / "lex.yaml"
    bad.write_text("entries:\n  - {term: A, say: x}\n  - {term: A, say: y}\n")
    with pytest.raises(LexiconError, match="duplicate"):
        load_lexicon(bad)


# ------------------------------------------------------------------ CLI


def test_cli_synth_caches_and_records_provenance(
    tmp_path: Path, cfg_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[FakeProvider] = []
    monkeypatch.setattr(service_mod, "default_registry", lambda: fake_registry(made))
    edition = tmp_path / "e.json"
    shutil.copy(FIXTURES / "normal.json", edition)
    runner = CliRunner()
    args = ["tts", "synth", str(edition), "--config", str(cfg_path), "--write"]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, args)
    assert second.exit_code == 0 and second.output.count("cached") == 7
    refs = json.loads(edition.read_text(encoding="utf-8"))["media"]["narration"]
    assert {r["voice"] for r in refs} == {"am_adam"} and refs[0]["tts_provider"] == "kokoro"
    Edition.model_validate_json(edition.read_text(encoding="utf-8"))  # still valid


def test_cli_synth_failure_says_web_only(
    tmp_path: Path, cfg_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(cfg: TTSConfig) -> FakeProvider:
        return FakeProvider("kokoro", fail=TTSProviderError("model missing"))

    monkeypatch.setattr(service_mod, "default_registry", lambda: {"kokoro": broken})
    result = CliRunner().invoke(
        app, ["tts", "synth", str(FIXTURES / "normal.json"), "--config", str(cfg_path)]
    )
    assert result.exit_code == 1 and "web-only" in result.output
