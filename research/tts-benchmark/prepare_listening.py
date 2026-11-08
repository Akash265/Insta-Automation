"""P1-40: build the blind listening clips from the benchmark output.

Copies each CPU candidate's main.wav and names.wav to listening/clips/<letter>-main.wav
and <letter>-names.wav under a random letter, and writes the sealed key with clip hashes
(committed, so the mapping can't be changed after scoring). Clips are git-ignored and
shared with listeners privately. No scores are produced here.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATES = [
    "kokoro-af_heart-cpu",
    "kokoro-am_adam-cpu",
    "kokoro-bf_emma-cpu",
    "piper-en_GB-cori-medium-cpu",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    clips = HERE / "listening" / "clips"
    key_path = HERE / "listening" / "KEY-do-not-open-until-scored.json"
    if key_path.exists():
        raise SystemExit("key already exists: the blind mapping must not be regenerated")
    clips.mkdir(parents=True, exist_ok=True)
    order = CANDIDATES[:]
    secrets.SystemRandom().shuffle(order)
    key: dict[str, object] = {"created_at": datetime.now(UTC).isoformat(), "clips": {}}
    for letter, cid in zip("ABCD", order, strict=True):
        entry = {"candidate": cid}
        for kind in ("main", "names"):
            src = HERE / "results" / cid / f"{kind}.wav"
            dst = clips / f"{letter}-{kind}.wav"
            shutil.copyfile(src, dst)
            entry[f"{kind}_sha256"] = sha(dst)
        key["clips"][letter] = entry  # type: ignore[index]
    key_path.write_text(json.dumps(key, indent=2) + "\n")
    print(f"clips written to {clips}; key sealed in {key_path.name} (do not open before scoring)")


if __name__ == "__main__":
    main()
