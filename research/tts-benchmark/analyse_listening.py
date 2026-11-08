"""P1-40: analyse the completed blind-listening scores (standard library only).

Usage (from research/tts-benchmark/):
    python3 analyse_listening.py                     # blind: results by clip letter only
    python3 analyse_listening.py --reveal            # after scoring: map letters to engines

Input: `results/listening-scores.csv`, which the founder assembles from the listeners'
sheets (same columns as `listening/scoring-sheet.csv`, listener codes only). At least 3
independent listeners (L1, L2, L3, ...) are required; the founder's own sheet, if any,
uses code F and does not count toward the 3. Output:
`results/listening-analysis.md`, which is also printed.

The answer key is read **only** with `--reveal`, and only if the scores are complete and
valid. Before mapping, the clip hashes are checked against the key, so the letters
still refer to the files the listeners heard. This script never writes scores.

Acceptance rules (ADR-004, listening/INSTRUCTIONS.md):
- naturalness: mean >= 3.5 and no listener below 3 (main clip);
- pronunciation: a name is wrong if >= 2 listeners flag it; >= 16/20 correct out of
  the box; no ordinary word flagged by >= 2 listeners (single flags are listed);
- artefacts: no `minor`/`major` artefact flagged by >= 2 listeners.
"All 20 fixable with lexicon entries" can't be judged from the sheet; it needs a
lexicon re-test of the flagged names.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMNS = (
    "listener_code",
    "clip",
    "naturalness_1to5",
    "mispronounced_terms",
    "other_mispronounced_words",
    "artefacts",
    "artefact_notes",
    "comments",
)
CLIPS = ("A", "B", "C", "D")
ARTEFACTS = ("none", "minor", "major")
MIN_LISTENERS = 3  # independent listeners, not counting the founder
FOUNDER = "F"  # the founder's own sheet, if any: included in results, not in the minimum
AGREE = 2  # listeners who must flag the same thing for it to count


class ScoresError(Exception):
    """The scoring sheet is incomplete or malformed."""


@dataclass
class ClipResult:
    clip: str
    scores: dict[str, int]
    wrong_names: list[str]
    single_flag_names: list[str]
    wrong_words: list[str]
    single_flag_words: list[str]
    artefact_flags: Counter[str] = field(default_factory=Counter)

    @property
    def mean(self) -> float:
        return sum(self.scores.values()) / len(self.scores)

    @property
    def names_correct(self) -> int:
        return 20 - len(self.wrong_names)

    @property
    def artefacts_flagged(self) -> int:
        return self.artefact_flags["minor"] + self.artefact_flags["major"]

    def checks(self) -> dict[str, bool]:
        return {
            "naturalness": self.mean >= 3.5 and min(self.scores.values()) >= 3,
            "names >= 16/20": self.names_correct >= 16,
            "ordinary words": not self.wrong_words,
            "artefacts": self.artefacts_flagged < AGREE,
        }


def _split(cell: str) -> list[str]:
    return [p.strip() for p in cell.split(";") if p.strip()]


def load_terms(path: Path) -> list[str]:
    terms = json.loads(path.read_text(encoding="utf-8"))["pronunciation_terms"]
    if len(terms) != 20:
        raise ScoresError(f"expected 20 pronunciation terms, found {len(terms)}")
    return list(terms)


def analyse(scores_path: Path, terms: list[str]) -> list[ClipResult]:
    if not scores_path.exists():
        raise ScoresError(f"{scores_path} not found: assemble the listeners' sheets first")
    with scores_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ScoresError(f"unexpected columns {reader.fieldnames}; expected {COLUMNS}")
        rows = list(reader)
    canon = {t.casefold(): t for t in terms}
    seen: set[tuple[str, str]] = set()
    by_clip: dict[str, list[dict[str, str]]] = {c: [] for c in CLIPS}
    problems: list[str] = []
    for n, row in enumerate(rows, start=2):
        code, clip = row["listener_code"].strip(), row["clip"].strip().upper()
        if not code:
            problems.append(f"line {n}: missing listener_code")
            continue
        if clip not in CLIPS:
            problems.append(f"line {n}: clip {row['clip']!r} is not one of {CLIPS}")
            continue
        if (code, clip) in seen:
            problems.append(f"line {n}: {code} scored clip {clip} twice")
        seen.add((code, clip))
        score = row["naturalness_1to5"].strip()
        if score not in {"1", "2", "3", "4", "5"}:
            problems.append(f"line {n}: naturalness {score!r} must be a whole number 1-5")
        if row["artefacts"].strip().lower() not in ARTEFACTS:
            problems.append(f"line {n}: artefacts {row['artefacts']!r} must be one of {ARTEFACTS}")
        for term in _split(row["mispronounced_terms"]):
            if term.casefold() not in canon:
                problems.append(f"line {n}: {term!r} is not one of the 20 names")
        by_clip[clip].append({**row, "listener_code": code})
    listeners = {code for code, _ in seen}
    independent = listeners - {FOUNDER}
    if len(independent) < MIN_LISTENERS:
        problems.append(
            f"{len(independent)} independent listener(s); at least {MIN_LISTENERS} are required"
            f" (code {FOUNDER} is the founder and does not count)"
        )
    for code in sorted(listeners):
        missing = [c for c in CLIPS if (code, c) not in seen]
        if missing:
            problems.append(f"{code} did not score clip(s) {', '.join(missing)}")
    if problems:
        raise ScoresError("\n".join(problems))

    results = []
    for clip in CLIPS:
        names: Counter[str] = Counter()
        words: Counter[str] = Counter()
        artefacts: Counter[str] = Counter()
        scores: dict[str, int] = {}
        for row in by_clip[clip]:
            scores[row["listener_code"]] = int(row["naturalness_1to5"])
            names.update({canon[t.casefold()] for t in _split(row["mispronounced_terms"])})
            words.update({w.casefold() for w in _split(row["other_mispronounced_words"])})
            artefacts[row["artefacts"].strip().lower()] += 1
        results.append(
            ClipResult(
                clip=clip,
                scores=scores,
                wrong_names=sorted(t for t, k in names.items() if k >= AGREE),
                single_flag_names=sorted(t for t, k in names.items() if k < AGREE),
                wrong_words=sorted(w for w, k in words.items() if k >= AGREE),
                single_flag_words=sorted(w for w, k in words.items() if k < AGREE),
                artefact_flags=artefacts,
            )
        )
    return results


def reveal(key_path: Path, clips_dir: Path) -> dict[str, str]:
    """Letter -> candidate, after checking the clips still match the sealed key."""
    key = json.loads(key_path.read_text(encoding="utf-8"))["clips"]
    mapping = {}
    for letter in CLIPS:
        entry = key[letter]
        for kind in ("main", "names"):
            clip = clips_dir / f"{letter}-{kind}.wav"
            if clip.exists():
                digest = hashlib.sha256(clip.read_bytes()).hexdigest()
                if digest != entry[f"{kind}_sha256"]:
                    raise ScoresError(f"{clip.name} does not match the sealed key")
        mapping[letter] = entry["candidate"]
    return mapping


def render(results: list[ClipResult], mapping: dict[str, str] | None) -> str:
    listeners = sorted({code for r in results for code in r.scores})
    lines = [
        "# P1-40 blind-listening analysis",
        "",
        f"Listeners: {len(listeners)} ({', '.join(listeners)}). A name, word or artefact "
        f"counts when >= {AGREE} listeners flag it.",
        "Mapping: " + ("revealed from the sealed key" if mapping else "**still blind**"),
        "",
        "| Clip | Engine | Naturalness mean (min) | Names correct | Wrong names | "
        "Wrong ordinary words | Artefacts flagged | Passes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        checks = r.checks()
        failed = [k for k, ok in checks.items() if not ok]
        verdict = "all" if not failed else "fails: " + ", ".join(failed)
        lines.append(
            f"| {r.clip} | {mapping[r.clip] if mapping else 'hidden'} "
            f"| {r.mean:.2f} ({min(r.scores.values())}) | {r.names_correct}/20 "
            f"| {'; '.join(r.wrong_names) or 'none'} | {'; '.join(r.wrong_words) or 'none'} "
            f"| {r.artefacts_flagged} (minor {r.artefact_flags['minor']}, "
            f"major {r.artefact_flags['major']}) | {verdict} |"
        )
    lines += ["", "Flagged by a single listener (for the lexicon, not the verdict):"]
    for r in results:
        single = r.single_flag_names + r.single_flag_words
        lines.append(f"- {r.clip}: {'; '.join(single) or 'none'}")
    lines += [
        "",
        "Not decided by this sheet: whether every wrong name is fixable with a lexicon "
        "entry (re-test the flagged names with lexicon entries before selection).",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyse P1-40 blind-listening scores.")
    parser.add_argument("--scores", type=Path, default=HERE / "results" / "listening-scores.csv")
    parser.add_argument("--terms", type=Path, default=HERE / "benchmark_text.json")
    parser.add_argument(
        "--key", type=Path, default=HERE / "listening" / "KEY-do-not-open-until-scored.json"
    )
    parser.add_argument("--clips", type=Path, default=HERE / "listening" / "clips")
    parser.add_argument("--out", type=Path, default=HERE / "results" / "listening-analysis.md")
    parser.add_argument("--reveal", action="store_true", help="map letters to engines")
    args = parser.parse_args(argv)
    try:
        results = analyse(args.scores, load_terms(args.terms))
        mapping = reveal(args.key, args.clips) if args.reveal else None
    except ScoresError as exc:
        print(f"REFUSED:\n{exc}")
        return 1
    text = render(results, mapping)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
