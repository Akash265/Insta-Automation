"""Pronunciation lexicon (`video_templates/lexicon.yaml`): whole-word respellings."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]


class LexiconError(ValueError):
    pass


@dataclass(frozen=True)
class Lexicon:
    entries: tuple[tuple[str, str], ...]  # (term, say)
    content_hash: str  # part of the cache key: editing the lexicon re-synthesises

    def apply(self, text: str) -> str:
        # Longest terms first, so "GPT-4o mini" would win over "GPT-4o".
        for term, say in sorted(self.entries, key=lambda e: -len(e[0])):
            text = re.sub(rf"(?<![\w-]){re.escape(term)}(?![\w-])", say, text)
        return text


def load_lexicon(path: Path) -> Lexicon:
    try:
        raw_text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(raw_text) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise LexiconError(f"cannot read {path}: {exc}") from exc
    entries = []
    seen: set[str] = set()
    for e in raw.get("entries") or []:
        term, say = str(e.get("term", "")).strip(), str(e.get("say", "")).strip()
        if not term or not say:
            raise LexiconError(f"{path}: every entry needs 'term' and 'say'")
        if term in seen:
            raise LexiconError(f"{path}: duplicate term {term!r}")
        seen.add(term)
        entries.append((term, say))
    digest = hashlib.sha256(repr(sorted(entries)).encode("utf-8")).hexdigest()
    return Lexicon(tuple(entries), digest)
