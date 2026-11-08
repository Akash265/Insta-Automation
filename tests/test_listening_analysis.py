"""P1-40: the listening analysis, on synthetic scores only (the real key is never read)."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.conftest import ROOT

BENCH = ROOT / "research" / "tts-benchmark"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "analyse_listening", BENCH / "analyse_listening.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up here
    spec.loader.exec_module(module)
    return module


al = _load()
TERMS = al.load_terms(BENCH / "benchmark_text.json")


def write_scores(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(al.COLUMNS)
        w.writerows(rows)
    return path


def full_sheet(listeners: tuple[str, ...] = ("L1", "L2", "L3")) -> list[list[str]]:
    rows = []
    for code in listeners:
        rows += [
            [code, "A", "4", "", "", "none", "", ""],
            [code, "B", "2" if code == "L1" else "4", "", "", "none", "", ""],
            [code, "C", "4", "Qwen;CUDA" if code != "L3" else "qwen", "", "minor", "", ""],
            [code, "D", "5", "Ollama" if code == "L1" else "", "", "none", "", ""],
        ]
    return rows


def test_terms_are_the_twenty_names() -> None:
    assert len(TERMS) == 20 and "Qwen" in TERMS and "GPT-4o" in TERMS


def test_committed_scoring_sheet_is_still_empty() -> None:
    text = (BENCH / "listening" / "scoring-sheet.csv").read_text(encoding="utf-8")
    assert text.strip() == ",".join(al.COLUMNS)


def test_agreement_rules(tmp_path: Path) -> None:
    results = {r.clip: r for r in al.analyse(write_scores(tmp_path / "s.csv", full_sheet()), TERMS)}
    assert all(results["A"].checks().values())
    assert not results["B"].checks()["naturalness"]  # one listener below 3
    assert results["C"].wrong_names == ["CUDA", "Qwen"]  # case-insensitive agreement
    assert results["C"].names_correct == 18 and not results["C"].checks()["artefacts"]
    assert results["D"].wrong_names == [] and results["D"].single_flag_names == ["Ollama"]


def test_incomplete_or_malformed_sheets_are_refused(tmp_path: Path) -> None:
    with pytest.raises(al.ScoresError, match="at least 3"):
        al.analyse(write_scores(tmp_path / "a.csv", full_sheet(("L1", "L2", "F"))), TERMS)
    rows = [*full_sheet()[:-1], ["L3", "D", "6", "Qwn", "", "loud", "", ""]]
    with pytest.raises(al.ScoresError) as exc:
        al.analyse(write_scores(tmp_path / "b.csv", rows), TERMS)
    message = str(exc.value)
    assert "1-5" in message and "not one of the 20 names" in message and "artefacts" in message
    with pytest.raises(al.ScoresError, match="did not score"):
        al.analyse(write_scores(tmp_path / "c.csv", full_sheet()[:-1]), TERMS)


def test_founder_sheet_is_included_but_not_counted(tmp_path: Path) -> None:
    results = al.analyse(
        write_scores(tmp_path / "s.csv", full_sheet(("L1", "L2", "L3", "F"))), TERMS
    )
    assert set(results[0].scores) == {"L1", "L2", "L3", "F"}


def test_cli_stays_blind_without_reveal(tmp_path: Path) -> None:
    scores = write_scores(tmp_path / "s.csv", full_sheet())
    out = tmp_path / "analysis.md"
    missing_key = tmp_path / "no-key.json"  # proves the key is not read
    argv = ["--scores", str(scores), "--out", str(out), "--key", str(missing_key)]
    assert al.main(argv) == 0
    assert "still blind" in out.read_text() and "hidden" in out.read_text()


def test_reveal_checks_clip_hashes(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    key: dict[str, dict[str, dict[str, str]]] = {"clips": {}}
    for letter in al.CLIPS:
        entry = {"candidate": f"engine-{letter}"}
        for kind in ("main", "names"):
            data = f"{letter}{kind}".encode()
            (clips / f"{letter}-{kind}.wav").write_bytes(data)
            entry[f"{kind}_sha256"] = hashlib.sha256(data).hexdigest()
        key["clips"][letter] = entry
    key_path = tmp_path / "key.json"
    key_path.write_text(json.dumps(key))
    assert al.reveal(key_path, clips)["C"] == "engine-C"
    (clips / "B-main.wav").write_bytes(b"swapped")
    with pytest.raises(al.ScoresError, match="does not match"):
        al.reveal(key_path, clips)
