"""P1-05: download exactly the model files under test and record their provenance.

Run with the benchmark environment: `uv run --no-sync python download_models.py`.
Files stay in the Hugging Face cache (outside git); the manifest records revision,
size and SHA-256 so every result can be traced to exact bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

FILES = {
    "hexgrad/Kokoro-82M": [
        "config.json",
        "kokoro-v1_0.pth",
        "voices/af_heart.pt",
        "voices/am_adam.pt",
        "voices/bf_emma.pt",
        "README.md",  # model card: licence evidence
        "VOICES.md",
    ],
    "rhasspy/piper-voices": [
        "en/en_GB/cori/medium/en_GB-cori-medium.onnx",
        "en/en_GB/cori/medium/en_GB-cori-medium.onnx.json",
        "en/en_GB/cori/medium/MODEL_CARD",  # voice licence evidence
    ],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    api = HfApi()
    manifest = []
    for repo, files in FILES.items():
        revision = api.model_info(repo).sha  # pin everything to one commit per repo
        for name in files:
            local = Path(hf_hub_download(repo, name, revision=revision))
            manifest.append(
                {
                    "repo": repo,
                    "revision": revision,
                    "file": name,
                    "bytes": local.stat().st_size,
                    "sha256": sha256(local),
                    "local_path": str(local),
                }
            )
            print(f"{repo}@{revision[:10]} {name} {local.stat().st_size:,} bytes")
    out = Path("results/model-manifest.json")
    out.write_text(json.dumps({"files": manifest}, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
