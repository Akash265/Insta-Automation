"""Append-only, tamper-evident error log (`experiment/error-log.csv`, task P1-19).

Every confirmed error is a row; a correction is a *new* row of kind `resolution` that
refers to the error. Rows are never edited or deleted (docs/VALIDATION_EXPERIMENT.md
§6, §9).

Three layers of protection:
1. **Hash chain.** Each row stores the previous row's hash and its own hash over all
   its values, so editing or reordering a row breaks the chain.
2. **Protected anchor.** The chain does not start from a well-known value. It starts
   from a random `genesis` created once (`brief experiment init-log`) and kept in
   `error-log.anchor.json`, together with **checkpoints** (row count + head hash)
   recorded automatically on every append (and on demand with `brief experiment
   checkpoint`). A log rebuilt from scratch fails the genesis check; a log with rows cut
   off the end fails the checkpoint check.
3. **Git.** The anchor file is committed. Verification compares it with the last
   committed version: the genesis must be unchanged and the committed checkpoints must
   still be present, so the anchor can't be quietly rewritten alongside the log.

Residual risk: rows and anchor changed *together before they are committed* can't be
told apart from honest history, so commit the log and anchor at least daily.
"""

from __future__ import annotations

import csv
import hashlib
import json
import secrets
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

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
SOURCES = ("auditor", "self", "panel", "founder")
SEVERITIES = ("critical", "material", "minor", "process")


class ErrorLogIntegrityError(Exception):
    """The log or its anchor was edited, reordered, truncated or rebuilt."""


@dataclass
class Anchor:
    genesis: str
    created_at: str
    checkpoints: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        data = {
            "genesis": self.genesis,
            "created_at": self.created_at,
            "checkpoints": self.checkpoints,
        }
        return json.dumps(data, indent=2) + "\n"

    @staticmethod
    def from_json(text: str) -> Anchor:
        d = json.loads(text)
        genesis = d["genesis"]
        if not (isinstance(genesis, str) and len(genesis) == 64):
            raise ErrorLogIntegrityError("anchor genesis must be 64 hex characters")
        return Anchor(genesis, d["created_at"], list(d.get("checkpoints", [])))


def anchor_path_for(log: Path) -> Path:
    return log.with_name(f"{log.stem}.anchor.json")


def load_anchor(log: Path) -> Anchor | None:
    path = anchor_path_for(log)
    if not path.exists():
        return None
    return Anchor.from_json(path.read_text(encoding="utf-8"))


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


def init_anchor(log: Path, now: datetime) -> Anchor:
    """Create the random genesis once, before the first row. Commit the anchor file."""
    if anchor_path_for(log).exists():
        raise ErrorLogIntegrityError("anchor already exists; it must never be recreated")
    if read_rows(log):
        raise ErrorLogIntegrityError("log already has rows; an anchor can't be added later")
    anchor = Anchor(secrets.token_hex(32), now.isoformat())
    path = anchor_path_for(log)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(anchor.to_json(), encoding="utf-8")
    return anchor


def verify(rows: Sequence[dict[str, str]], anchor: Anchor | None) -> list[str]:
    """Problems with the rows against the anchor; an empty list means intact."""
    if anchor is None:
        return ["no anchor file: run `brief experiment init-log` before the first entry "
                "and commit error-log.anchor.json"]  # fmt: skip
    problems: list[str] = []
    prev = anchor.genesis
    error_ids: set[str] = set()
    for n, row in enumerate(rows, start=1):
        expected_id = f"E{n:04d}"
        if row["entry_id"] != expected_id:
            problems.append(f"row {n}: entry_id {row['entry_id']!r}, expected {expected_id}")
        if row["prev_hash"] != prev:
            label = "genesis (log rebuilt?)" if n == 1 else "previous-row hash"
            problems.append(f"row {n} ({row['entry_id']}): {label} does not match")
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
    for cp in anchor.checkpoints:
        count, head = int(cp["count"]), str(cp["head_hash"])
        if count > len(rows):
            problems.append(f"log truncated: checkpoint expects {count} rows, found {len(rows)}")
        elif count > 0 and rows[count - 1]["row_hash"] != head:
            problems.append(f"checkpoint at row {count} does not match the log")
    return problems


def verify_anchor_in_git(log: Path) -> tuple[list[str], list[str]]:
    """Compare the anchor with its last committed version. Returns (problems, warnings)."""
    path = anchor_path_for(log).resolve()
    if not path.exists():
        return [], []
    try:
        top = subprocess.run(  # noqa: S603 - fixed git arguments, no shell
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],  # noqa: S607
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()  # fmt: skip
        rel = path.relative_to(Path(top).resolve()).as_posix()
        committed = subprocess.run(  # noqa: S603 - fixed git arguments, no shell
            ["git", "-C", top, "show", f"HEAD:{rel}"],  # noqa: S607
            capture_output=True, text=True, check=False, timeout=10,
        )  # fmt: skip
    except (OSError, ValueError, subprocess.SubprocessError):
        return [], ["anchor is not inside a git repository, so it is not protected by history"]
    if committed.returncode != 0:
        return [], ["anchor is not committed yet: commit error-log.anchor.json to protect it"]
    old = Anchor.from_json(committed.stdout)
    new = Anchor.from_json(path.read_text(encoding="utf-8"))
    problems = []
    if old.genesis != new.genesis:
        problems.append("anchor genesis differs from the committed version")
    if new.checkpoints[: len(old.checkpoints)] != old.checkpoints:
        problems.append("committed checkpoints were removed or changed in the anchor")
    return problems, []


def full_verify(log: Path) -> tuple[list[str], list[str]]:
    """Chain + anchor + git checks. Returns (problems, warnings)."""
    anchor = load_anchor(log)
    problems = verify(read_rows(log), anchor)
    git_problems, warnings = verify_anchor_in_git(log)
    return problems + git_problems, warnings


def _append(path: Path, values: dict[str, str]) -> str:
    rows = read_rows(path)
    anchor = load_anchor(path)
    problems = verify(rows, anchor)
    if problems or anchor is None:
        raise ErrorLogIntegrityError("; ".join(problems))
    prev = rows[-1]["row_hash"] if rows else anchor.genesis
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
    # Every append also checkpoints, so cutting rows off the end is detectable.
    anchor.checkpoints.append(
        {"count": len(rows) + 1, "head_hash": row[-1], "at": values.get("logged_at", "")}
    )
    anchor_path_for(path).write_text(anchor.to_json(), encoding="utf-8")
    return values["entry_id"]


def add_checkpoint(log: Path, now: datetime) -> dict[str, Any] | None:
    """Record the current row count and head hash in the anchor (then commit it)."""
    rows = read_rows(log)
    anchor = load_anchor(log)
    problems = verify(rows, anchor)
    if problems or anchor is None:
        raise ErrorLogIntegrityError("; ".join(problems))
    last = anchor.checkpoints[-1]["count"] if anchor.checkpoints else 0
    if not rows or len(rows) <= last:
        return None
    cp = {"count": len(rows), "head_hash": rows[-1]["row_hash"], "at": now.isoformat()}
    anchor.checkpoints.append(cp)
    anchor_path_for(log).write_text(anchor.to_json(), encoding="utf-8")
    return cp


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
