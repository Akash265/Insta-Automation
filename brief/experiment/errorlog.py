"""Append-only, tamper-evident error log (`experiment/error-log.csv`, task P1-19).

Every confirmed error is a row; a correction is a *new* row of kind `resolution` that
refers to the error. Rows are never edited or deleted. Each row stores the previous
row's hash and its own hash over all its values, so any edit, deletion or reordering
breaks the chain and `brief report experiment` refuses to run
(docs/VALIDATION_EXPERIMENT.md §6, §9).
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

COLUMNS = (
    "entry_id",
    "kind",
    "logged_at",
    "issue_key",
    "story_rank",
    "source",
    "severity",
    "description",
    "evidence_url",
    "caught_pre_publication",
    "refers_to",
    "correction_ref",
    "prev_hash",
    "row_hash",
)
HASHED = COLUMNS[:-2]
GENESIS = "0" * 64
SOURCES = ("auditor", "self", "panel", "founder")
SEVERITIES = ("critical", "material", "minor", "process")


class ErrorLogIntegrityError(Exception):
    """The log was edited, reordered or truncated."""


def _row_hash(prev_hash: str, values: Sequence[str]) -> str:
    payload = "\x1f".join([prev_hash, *values])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ErrorLogIntegrityError(f"{path}: unexpected columns {reader.fieldnames}")
        return list(reader)


def verify(rows: Sequence[dict[str, str]]) -> list[str]:
    """Return integrity problems; an empty list means the chain is intact."""
    problems: list[str] = []
    prev = GENESIS
    error_ids: set[str] = set()
    for n, row in enumerate(rows, start=1):
        expected_id = f"E{n:04d}"
        if row["entry_id"] != expected_id:
            problems.append(f"row {n}: entry_id {row['entry_id']!r}, expected {expected_id}")
        if row["prev_hash"] != prev:
            problems.append(f"row {n} ({row['entry_id']}): previous-row hash does not match")
        values = [row[c] for c in HASHED]
        if row["row_hash"] != _row_hash(row["prev_hash"], values):
            problems.append(f"row {n} ({row['entry_id']}): contents were edited")
        if row["kind"] == "error":
            error_ids.add(row["entry_id"])
        elif row["kind"] == "resolution":
            if row["refers_to"] not in error_ids:
                problems.append(f"row {n}: resolution refers to unknown error {row['refers_to']!r}")
        else:
            problems.append(f"row {n}: unknown kind {row['kind']!r}")
        prev = row["row_hash"]
    return problems


def _append(path: Path, values: dict[str, str]) -> str:
    rows = read_rows(path)
    problems = verify(rows)
    if problems:
        raise ErrorLogIntegrityError("; ".join(problems))
    prev = rows[-1]["row_hash"] if rows else GENESIS
    values = {**values, "entry_id": f"E{len(rows) + 1:04d}", "prev_hash": prev}
    ordered = [values.get(c, "") for c in HASHED]
    row = [*ordered, prev, _row_hash(prev, ordered)]
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        if new_file:
            writer.writerow(COLUMNS)
        writer.writerow(row)
    return values["entry_id"]


def append_error(
    path: Path,
    *,
    issue_key: str,
    source: str,
    severity: str,
    description: str,
    logged_at: datetime,
    story_rank: int | None = None,
    evidence_url: str = "",
    caught_pre_publication: bool = False,
) -> str:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    if logged_at.tzinfo is None:
        raise ValueError("logged_at must include a timezone")
    return _append(
        path,
        {
            "kind": "error",
            "logged_at": logged_at.isoformat(),
            "issue_key": issue_key,
            "story_rank": "" if story_rank is None else str(story_rank),
            "source": source,
            "severity": severity,
            "description": description,
            "evidence_url": evidence_url,
            "caught_pre_publication": "true" if caught_pre_publication else "false",
        },
    )


def append_resolution(
    path: Path, *, refers_to: str, correction_ref: str, description: str, logged_at: datetime
) -> str:
    if logged_at.tzinfo is None:
        raise ValueError("logged_at must include a timezone")
    rows = read_rows(path)
    target = next((r for r in rows if r["entry_id"] == refers_to and r["kind"] == "error"), None)
    if target is None:
        raise ValueError(f"no error {refers_to!r} in {path}")
    return _append(
        path,
        {
            "kind": "resolution",
            "logged_at": logged_at.isoformat(),
            "issue_key": target["issue_key"],
            "story_rank": target["story_rank"],
            "severity": target["severity"],
            "description": description,
            "refers_to": refers_to,
            "correction_ref": correction_ref,
        },
    )


@dataclass(frozen=True)
class ErrorSummary:
    total_material_or_critical: int
    unresolved_material_or_critical: int
    minor: int
    caught_pre_publication: int
    unresolved_ids: tuple[str, ...]


def summarize(rows: Sequence[dict[str, str]]) -> ErrorSummary:
    errors = [r for r in rows if r["kind"] == "error"]
    resolved = {r["refers_to"] for r in rows if r["kind"] == "resolution"}
    serious = [r for r in errors if r["severity"] in ("material", "critical")]
    unresolved = tuple(r["entry_id"] for r in serious if r["entry_id"] not in resolved)
    return ErrorSummary(
        total_material_or_critical=len(serious),
        unresolved_material_or_critical=len(unresolved),
        minor=sum(1 for r in errors if r["severity"] == "minor"),
        caught_pre_publication=sum(1 for r in errors if r["caught_pre_publication"] == "true"),
        unresolved_ids=unresolved,
    )
