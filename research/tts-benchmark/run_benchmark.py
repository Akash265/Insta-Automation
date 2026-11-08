"""P1-05 controlled local TTS benchmark (ADR-004). Benchmark only: not production narration.

Usage (benchmark environment, after download_models.py):
    uv run --no-sync python run_benchmark.py              # all candidates
    uv run --no-sync python run_benchmark.py --only kokoro-af_heart-cpu

Each candidate runs in its own child process (so peak memory is per engine), fully
offline: models load from the hashed local files in results/model-manifest.json, the
Hugging Face hub is in offline mode, and during the 20-run reliability test a socket
guard refuses any non-loopback connection.

Machine measurements only. Naturalness, pronunciation correctness and audible
artefacts are judged by human listeners (P1-40) and are never filled in here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
CANDIDATES: dict[str, dict[str, str]] = {
    "kokoro-af_heart-cpu": {"engine": "kokoro", "voice": "af_heart", "lang": "a", "device": "cpu"},
    "kokoro-am_adam-cpu": {"engine": "kokoro", "voice": "am_adam", "lang": "a", "device": "cpu"},
    "kokoro-bf_emma-cpu": {"engine": "kokoro", "voice": "bf_emma", "lang": "b", "device": "cpu"},
    "kokoro-af_heart-mps": {"engine": "kokoro", "voice": "af_heart", "lang": "a", "device": "mps"},
    "piper-en_GB-cori-medium-cpu": {
        "engine": "piper",
        "voice": "en_GB-cori-medium",
        "device": "cpu",
    },
}


def manifest_path(repo: str, file: str) -> Path:
    data = json.loads((RESULTS / "model-manifest.json").read_text())
    for f in data["files"]:
        if f["repo"] == repo and f["file"] == file:
            return Path(f["local_path"])
    raise SystemExit(f"{repo}/{file} not in manifest: run download_models.py first")


def peak_rss_mb() -> float:
    # macOS reports ru_maxrss in bytes (Linux: kilobytes).
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def pcm16(audio: Any) -> tuple[bytes, int]:
    """float [-1, 1] numpy array -> (int16 PCM bytes, clipped-sample count)."""
    import numpy as np

    arr = np.asarray(audio, dtype=np.float32)
    clipped = int(np.sum(np.abs(arr) >= 0.999))
    ints = (np.clip(arr, -1.0, 1.0) * 32767.0).astype("<i2")
    return ints.tobytes(), clipped


def write_wav(path: Path, pcm: bytes, rate: int) -> None:
    import wave

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


class NetworkBlockedError(RuntimeError):
    pass


def block_network() -> None:
    """Refuse every non-loopback connection for the rest of this process."""
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            raise NetworkBlockedError(f"network access attempted: {address}")
        return real_connect(self, address)

    socket.socket.connect = guarded  # type: ignore[method-assign]


class KokoroEngine:
    def __init__(self, voice: str, lang: str, device: str) -> None:
        if device == "mps":
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        from kokoro import KModel, KPipeline

        repo = "hexgrad/Kokoro-82M"
        model = (
            KModel(
                repo_id=repo,
                config=str(manifest_path(repo, "config.json")),
                model=str(manifest_path(repo, "kokoro-v1_0.pth")),
            )
            .to(device)
            .eval()
        )
        self.pipeline = KPipeline(lang_code=lang, repo_id=repo, model=model, device=device)
        self.voice = str(manifest_path(repo, f"voices/{voice}.pt"))
        self.rate = 24000

    def synth(self, text: str) -> tuple[Any, list[str]]:
        import numpy as np

        audio, phonemes = [], []
        for r in self.pipeline(text, voice=self.voice, speed=1, split_pattern=r"\n+"):
            if r.audio is not None:
                audio.append(r.audio.detach().cpu().numpy())
            phonemes.append(r.phonemes)
        return np.concatenate(audio), phonemes

    def phonemize(self, text: str) -> str:
        ps, _ = self.pipeline.g2p(text)
        return str(ps)


class PiperEngine:
    def __init__(self, voice: str) -> None:
        from piper import PiperVoice

        repo = "rhasspy/piper-voices"
        base = f"en/en_GB/cori/medium/{voice}"
        self.voice = PiperVoice.load(
            manifest_path(repo, f"{base}.onnx"), manifest_path(repo, f"{base}.onnx.json")
        )
        self.rate = int(self.voice.config.sample_rate)

    def synth(self, text: str) -> tuple[Any, list[str]]:
        import numpy as np

        chunks = [c.audio_float_array for c in self.voice.synthesize(text)]
        return np.concatenate(chunks), [self.phonemize(text)]

    def phonemize(self, text: str) -> str:
        return " | ".join("".join(p) for p in self.voice.phonemize(text))


def run_child(cid: str) -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    spec = CANDIDATES[cid]
    text = json.loads((HERE / "benchmark_text.json").read_text())
    segments: list[str] = text["main_script_segments"]
    passage: list[str] = text["pronunciation_passage"]
    out = RESULTS / cid
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    engine: Any = (
        KokoroEngine(spec["voice"], spec["lang"], spec["device"])
        if spec["engine"] == "kokoro"
        else PiperEngine(spec["voice"])
    )
    engine.synth("Warm up.")  # first call includes lazy initialisation
    load_s = time.perf_counter() - t0

    script = "\n".join(segments)
    runs = []
    first_pcm = b""
    for i in range(3):
        t = time.perf_counter()
        audio, _ = engine.synth(script)
        elapsed = time.perf_counter() - t
        pcm, clipped = pcm16(audio)
        if i == 0:
            first_pcm = pcm
            write_wav(out / "main.wav", pcm, engine.rate)
        runs.append(
            {
                "seconds": round(elapsed, 3),
                "audio_seconds": round(len(audio) / engine.rate, 2),
                "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
                "clipped_samples": clipped,
            }
        )

    names_audio, _ = engine.synth("\n".join(passage))
    names_pcm, names_clipped = pcm16(names_audio)
    write_wav(out / "names.wav", names_pcm, engine.rate)
    phonemes = {s: engine.phonemize(s) for s in passage}

    # 20 consecutive offline generations through the same engine, network blocked.
    block_network()
    pool = (segments + passage) * 2
    reliability = []
    for n, seg in enumerate(pool[:20], start=1):
        t = time.perf_counter()
        try:
            audio, _ = engine.synth(seg)
            ok = len(audio) > 0
            err = None if ok else "empty audio"
        except Exception as exc:
            ok, err = False, f"{type(exc).__name__}: {exc}"
        reliability.append(
            {"n": n, "ok": ok, "seconds": round(time.perf_counter() - t, 3), "error": err}
        )

    metrics = {
        "candidate": cid,
        "spec": spec,
        "sample_rate": engine.rate,
        "load_and_warmup_seconds": round(load_s, 2),
        "full_script_runs": runs,
        "full_script_median_seconds": round(statistics.median(r["seconds"] for r in runs), 3),
        "deterministic_across_3_runs": len({r["pcm_sha256"] for r in runs}) == 1,
        "main_wav_sha256": hashlib.sha256(first_pcm).hexdigest(),
        "names_clipped_samples": names_clipped,
        "names_audio_seconds": round(len(names_audio) / engine.rate, 2),
        "phonemes_by_sentence": phonemes,
        "offline_reliability": {
            "generations": len(reliability),
            "succeeded": sum(1 for r in reliability if r["ok"]),
            "runs": reliability,
        },
        "peak_rss_mb": round(peak_rss_mb(), 1),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")


def loudness(path: Path, normalise: bool) -> dict[str, float | None]:
    """Integrated loudness and true peak via FFmpeg ebur128 (optionally after loudnorm)."""
    chain = "loudnorm=I=-14:TP=-1:LRA=11,ebur128=peak=true" if normalise else "ebur128=peak=true"
    proc = subprocess.run(  # noqa: S603 - fixed arguments
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", chain,  # noqa: S607
         "-ar", "48000", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    summary = proc.stderr[proc.stderr.rfind("Summary:") :]

    def grab(label: str) -> float | None:
        for line in summary.splitlines():
            if line.strip().startswith(label):
                try:
                    return float(line.split(":")[1].split()[0])
                except (IndexError, ValueError):
                    return None
        return None

    return {"integrated_lufs": grab("I:"), "true_peak_dbtp": grab("Peak:")}


def probe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(  # noqa: S603 - fixed arguments
        ["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels,codec_name",  # noqa: S607
         "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    data = json.loads(proc.stdout)
    s = data["streams"][0]
    return {
        "codec": s["codec_name"],
        "sample_rate": int(s["sample_rate"]),
        "channels": int(s["channels"]),
        "duration_s": round(float(data["format"]["duration"]), 2),
    }


def hardware() -> dict[str, str]:
    def sysctl(key: str) -> str:
        return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True,  # noqa: S603, S607
                              check=False).stdout.strip()  # fmt: skip

    return {
        "cpu": sysctl("machdep.cpu.brand_string"),
        "memory_gb": f"{int(sysctl('hw.memsize') or 0) / 1024**3:.0f}",
        "macos": platform.mac_ver()[0],
        "python": platform.python_version(),
    }


def run_parent(only: list[str]) -> None:
    summary: dict[str, Any] = {"hardware": hardware(), "candidates": {}}
    for cid in only or list(CANDIDATES):
        print(f"--- {cid}", flush=True)
        t = time.perf_counter()
        proc = subprocess.run([sys.executable, __file__, "--child", cid],  # noqa: S603
                              capture_output=True, text=True, check=False)  # fmt: skip
        if proc.returncode != 0:
            summary["candidates"][cid] = {
                "error": proc.stderr[-2000:],
                "wall_seconds": round(time.perf_counter() - t, 1),
            }
            print(f"FAILED ({proc.returncode})", flush=True)
            continue
        m = json.loads((RESULTS / cid / "metrics.json").read_text())
        main = RESULTS / cid / "main.wav"
        m["main_wav_probe"] = probe(main)
        m["main_raw_loudness"] = loudness(main, normalise=False)
        m["main_after_loudnorm_minus14"] = loudness(main, normalise=True)
        (RESULTS / cid / "metrics.json").write_text(
            json.dumps(m, indent=2, ensure_ascii=False) + "\n"
        )
        rel = m["offline_reliability"]
        summary["candidates"][cid] = {
            "sample_rate": m["sample_rate"],
            "load_and_warmup_seconds": m["load_and_warmup_seconds"],
            "full_script_median_seconds": m["full_script_median_seconds"],
            "audio_seconds": m["full_script_runs"][0]["audio_seconds"],
            "deterministic_across_3_runs": m["deterministic_across_3_runs"],
            "peak_rss_mb": m["peak_rss_mb"],
            "clipped_samples_main": m["full_script_runs"][0]["clipped_samples"],
            "main_wav_probe": m["main_wav_probe"],
            "main_raw_loudness": m["main_raw_loudness"],
            "main_after_loudnorm_minus14": m["main_after_loudnorm_minus14"],
            "offline_20_runs": f"{rel['succeeded']}/{rel['generations']}",
        }
        print(json.dumps(summary["candidates"][cid]), flush=True)
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--child")
    ap.add_argument("--only", nargs="*", default=[])
    args = ap.parse_args()
    if args.child:
        run_child(args.child)
    else:
        run_parent(args.only)
