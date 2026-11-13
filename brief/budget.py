"""Budget periods, spending caps and the ₹15,000 ceiling (task P1-36).

- Caps are defined per plan window (preparation, Days 1-30, 31-60, 61-90) in
  `config/budget_periods.yaml`, so code caps match the cash model one-to-one
  (docs/IMPLEMENTATION_STRATEGY.md §6).
- Paid API calls (LLM, voice) are logged to an append-only JSON-lines usage ledger.
  Other cash (domain, VPS, optional items) is logged by hand in a CSV cash ledger.
- Projected max = actual spend + every remaining cap of periods not yet ended
  + the unspent part of planned fixed items. Optional spend is allowed only while the
  projected max stays within the ceiling, and is frozen once actual spend passes the
  freeze threshold before the freeze day.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal, cast
from zoneinfo import ZoneInfo

import yaml  # type: ignore[import-untyped]

IST = ZoneInfo("Asia/Kolkata")
Category = Literal["llm", "tts"]
CashCategory = Literal["one_time", "infrastructure", "optional", "other"]
CASH_CATEGORIES: tuple[str, ...] = ("one_time", "infrastructure", "optional", "other")
DEFAULT_CONFIG = Path("config/budget_periods.yaml")
DEFAULT_USAGE = Path("finance/usage-ledger.jsonl")
DEFAULT_CASH = Path("finance/cash-ledger.csv")


class BudgetConfigError(ValueError):
    pass


class BudgetExceededError(Exception):
    pass


@dataclass(frozen=True)
class Period:
    id: str
    first_day: int | None  # None = open start (preparation: everything before Day 1)
    last_day: int
    llm_cap_usd: float
    tts_cap_usd: float
    llm_daily_cap_usd: float | None = None  # overrides the global daily cap in this period

    def contains(self, day: int) -> bool:
        low = -math.inf if self.first_day is None else self.first_day
        return low <= day <= self.last_day

    def cap(self, category: Category) -> float:
        return self.llm_cap_usd if category == "llm" else self.tts_cap_usd


@dataclass(frozen=True)
class PlannedItem:
    max_inr: float
    kind: Literal["one_off", "recurring"]


@dataclass(frozen=True)
class BudgetConfig:
    inr_per_usd: float
    ceiling_inr: float
    freeze_threshold_inr: float
    freeze_before_day: int
    day1: date | None
    llm_daily_cap_usd: float
    periods: tuple[Period, ...]
    planned_cash: dict[str, PlannedItem]


def load_config(path: Path = DEFAULT_CONFIG) -> BudgetConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BudgetConfigError(f"cannot read {path}: {exc}") from exc
    try:
        periods = tuple(
            Period(
                id=str(p["id"]),
                first_day=None if p["first_day"] is None else int(p["first_day"]),
                last_day=int(p["last_day"]),
                llm_cap_usd=float(p["llm_cap_usd"]),
                tts_cap_usd=float(p["tts_cap_usd"]),
                llm_daily_cap_usd=(
                    None if p.get("llm_daily_cap_usd") is None else float(p["llm_daily_cap_usd"])
                ),
            )
            for p in raw["periods"]
        )
        day1_raw = raw.get("day1")
        config = BudgetConfig(
            inr_per_usd=float(raw["inr_per_usd"]),
            ceiling_inr=float(raw["ceiling_inr"]),
            freeze_threshold_inr=float(raw["freeze"]["threshold_inr"]),
            freeze_before_day=int(raw["freeze"]["before_day"]),
            day1=None if day1_raw is None else date.fromisoformat(str(day1_raw)),
            llm_daily_cap_usd=float(raw["llm_daily_cap_usd"]),
            periods=periods,
            planned_cash={
                str(k): _planned_item(str(k), v) for k, v in (raw.get("planned_cash") or {}).items()
            },
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BudgetConfigError(f"invalid budget config {path}: {exc}") from exc
    _check_periods(config.periods)
    return config


def _planned_item(name: str, raw: dict[str, object]) -> PlannedItem:
    kind = raw.get("kind")
    if kind not in ("one_off", "recurring"):
        raise BudgetConfigError(f"planned item {name!r}: kind must be one_off or recurring")
    return PlannedItem(max_inr=float(str(raw["max_inr"])), kind=kind)


def _check_periods(periods: tuple[Period, ...]) -> None:
    if not periods or periods[0].first_day is not None:
        raise BudgetConfigError("the first period must be the open-start preparation period")
    for prev, nxt in itertools.pairwise(periods):
        if nxt.first_day != prev.last_day + 1:
            raise BudgetConfigError(f"periods must be contiguous: {prev.id} -> {nxt.id}")
    for p in periods:
        if p.llm_cap_usd < 0 or p.tts_cap_usd < 0:
            raise BudgetConfigError(f"negative cap in period {p.id}")


@dataclass(frozen=True)
class UsageEntry:
    at: datetime
    category: Category
    provider: str
    operation: str
    cost_usd: float
    status: Literal["ok", "error", "blocked_by_budget"] = "ok"
    model: str | None = None
    request_id: str | None = None
    note: str | None = None

    def to_json(self) -> str:
        data = {
            "at": self.at.isoformat(),
            "category": self.category,
            "provider": self.provider,
            "operation": self.operation,
            "cost_usd": self.cost_usd,
            "status": self.status,
            "model": self.model,
            "request_id": self.request_id,
            "note": self.note,
        }
        return json.dumps(data, sort_keys=True)

    @staticmethod
    def from_json(line: str) -> UsageEntry:
        d = json.loads(line)
        at = datetime.fromisoformat(d["at"])
        if at.tzinfo is None:
            raise ValueError("usage ledger timestamps must include a timezone")
        if d["category"] not in ("llm", "tts"):
            raise ValueError(f"unknown usage category {d['category']!r}")
        return UsageEntry(
            at=at,
            category=d["category"],
            provider=d["provider"],
            operation=d["operation"],
            cost_usd=float(d["cost_usd"]),
            status=d.get("status", "ok"),
            model=d.get("model"),
            request_id=d.get("request_id"),
            note=d.get("note"),
        )


@dataclass(frozen=True)
class CashEntry:
    day: date
    category: CashCategory
    item: str
    amount_inr: float
    note: str = ""


@dataclass
class CostReport:
    today: date
    day_index: int | None
    period_id: str | None
    usage_inr: dict[str, float]
    cash_inr: dict[str, float]
    actual_total_inr: float
    periods: list[tuple[Period, float, float]]  # (period, llm spent USD, tts spent USD)
    remaining_caps_inr: float
    planned_remaining_inr: float
    projected_max_inr: float
    ceiling_inr: float
    headroom_inr: float
    frozen: bool
    freeze_threshold_inr: float
    freeze_before_day: int
    notes: list[str] = field(default_factory=list)

    @property
    def optional_allowed_up_to_inr(self) -> float:
        return 0.0 if self.frozen else max(0.0, self.headroom_inr)


def _inr(value: float) -> str:
    return f"₹{value:,.0f}"


class Budget:
    def __init__(
        self,
        config: BudgetConfig,
        usage_path: Path = DEFAULT_USAGE,
        cash_path: Path = DEFAULT_CASH,
    ) -> None:
        self.config = config
        self.usage_path = usage_path
        self.cash_path = cash_path

    # ---- calendar ---------------------------------------------------------------
    def day_index(self, d: date) -> int | None:
        if self.config.day1 is None:
            return None
        return (d - self.config.day1).days + 1

    def period_for(self, d: date) -> Period | None:
        idx = self.day_index(d)
        if idx is None:
            return self.config.periods[0]  # Day 1 not set yet: still preparing
        return next((p for p in self.config.periods if p.contains(idx)), None)

    def _ended(self, period: Period, today: date) -> bool:
        idx = self.day_index(today)
        return idx is not None and idx > period.last_day

    # ---- ledgers ----------------------------------------------------------------
    def usage(self) -> list[UsageEntry]:
        if not self.usage_path.exists():
            return []
        lines = self.usage_path.read_text(encoding="utf-8").splitlines()
        return [UsageEntry.from_json(line) for line in lines if line.strip()]

    def cash(self) -> list[CashEntry]:
        if not self.cash_path.exists():
            return []
        with self.cash_path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        entries = []
        for n, row in enumerate(rows, start=2):
            category = row.get("category", "")
            if category not in CASH_CATEGORIES:
                raise BudgetConfigError(f"{self.cash_path}:{n}: unknown category {category!r}")
            entries.append(
                CashEntry(
                    day=date.fromisoformat(row["date"]),
                    category=cast(CashCategory, category),
                    item=row["item"].strip(),
                    amount_inr=float(row["amount_inr"]),
                    note=row.get("note", "") or "",
                )
            )
        return entries

    def record(self, entry: UsageEntry) -> None:
        """Append one usage entry (the ledger is append-only)."""
        self.usage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.usage_path.open("a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")

    # ---- spend ------------------------------------------------------------------
    def _local_date(self, at: datetime) -> date:
        return at.astimezone(IST).date()

    def spent_usd(
        self, period: Period, category: Category, entries: list[UsageEntry] | None = None
    ) -> float:
        rows = self.usage() if entries is None else entries
        return sum(
            e.cost_usd
            for e in rows
            if e.status == "ok"
            and e.category == category
            and self.period_for(self._local_date(e.at)) == period
        )

    def check(
        self,
        category: Category,
        estimated_usd: float,
        when: datetime | None = None,
        provider: str = "",
        operation: str = "",
    ) -> None:
        """Raise BudgetExceededError (and log the blocked call) if the call would break a cap."""
        moment = when or datetime.now(IST)
        day = self._local_date(moment)
        period = self.period_for(day)
        entries = self.usage()
        reason: str | None = None
        if period is None:
            reason = "date is outside the configured budget periods; extend the config first"
        else:
            spent = self.spent_usd(period, category, entries)
            cap = period.cap(category)
            if spent + estimated_usd > cap + 1e-9:
                reason = (
                    f"{category} cap for {period.id} is ${cap:.2f}; "
                    f"spent ${spent:.2f} + this call ${estimated_usd:.2f}"
                )
            elif category == "llm":
                today_spent = sum(
                    e.cost_usd
                    for e in entries
                    if e.status == "ok" and e.category == "llm" and self._local_date(e.at) == day
                )
                daily_cap = (
                    period.llm_daily_cap_usd
                    if period.llm_daily_cap_usd is not None
                    else self.config.llm_daily_cap_usd
                )
                if today_spent + estimated_usd > daily_cap + 1e-9:
                    reason = (
                        f"daily LLM cap is ${daily_cap:.2f}; "
                        f"spent ${today_spent:.2f} today + this call ${estimated_usd:.2f}"
                    )
        if reason is not None:
            self.record(
                UsageEntry(
                    at=moment,
                    category=category,
                    provider=provider or "unknown",
                    operation=operation or "unknown",
                    cost_usd=0.0,
                    status="blocked_by_budget",
                    note=reason,
                )
            )
            raise BudgetExceededError(reason)

    # ---- report -----------------------------------------------------------------
    def report(self, today: date) -> CostReport:
        cfg = self.config
        fx = cfg.inr_per_usd
        entries = self.usage()
        cash = self.cash()

        usage_inr = {"llm": 0.0, "tts": 0.0}
        for e in entries:
            if e.status == "ok":
                usage_inr[e.category] += e.cost_usd * fx
        cash_inr = {c: 0.0 for c in CASH_CATEGORIES}
        for c in cash:
            cash_inr[c.category] += c.amount_inr
        actual = sum(usage_inr.values()) + sum(cash_inr.values())

        rows: list[tuple[Period, float, float]] = []
        remaining_caps = 0.0
        for p in cfg.periods:
            llm = self.spent_usd(p, "llm", entries)
            tts = self.spent_usd(p, "tts", entries)
            rows.append((p, llm, tts))
            if not self._ended(p, today):
                remaining_caps += (
                    max(0.0, p.llm_cap_usd - llm) + max(0.0, p.tts_cap_usd - tts)
                ) * fx

        planned_remaining = 0.0
        for item, planned in cfg.planned_cash.items():
            paid = [c.amount_inr for c in cash if c.item == item]
            if planned.kind == "one_off" and paid:
                continue  # bought: the unused allowance is released
            planned_remaining += max(0.0, planned.max_inr - sum(paid))

        projected = actual + remaining_caps + planned_remaining

        def before_freeze_day(d: date) -> bool:
            idx = self.day_index(d)
            return idx is None or idx < cfg.freeze_before_day

        spent_before = sum(
            e.cost_usd * fx
            for e in entries
            if e.status == "ok" and before_freeze_day(self._local_date(e.at))
        ) + sum(c.amount_inr for c in cash if before_freeze_day(c.day))
        frozen = spent_before > cfg.freeze_threshold_inr

        notes = []
        if cfg.day1 is None:
            notes.append("Day 1 is not set (config day1): everything counts as preparation.")
        period = self.period_for(today)
        return CostReport(
            today=today,
            day_index=self.day_index(today),
            period_id=period.id if period else None,
            usage_inr=usage_inr,
            cash_inr=cash_inr,
            actual_total_inr=actual,
            periods=rows,
            remaining_caps_inr=remaining_caps,
            planned_remaining_inr=planned_remaining,
            projected_max_inr=projected,
            ceiling_inr=cfg.ceiling_inr,
            headroom_inr=cfg.ceiling_inr - projected,
            frozen=frozen,
            freeze_threshold_inr=cfg.freeze_threshold_inr,
            freeze_before_day=cfg.freeze_before_day,
            notes=notes,
        )


def render_report(r: CostReport) -> str:
    day = f"Day {r.day_index}" if r.day_index is not None else "Day 1 not set"
    period = r.period_id or "after Day 90"
    lines = [
        f"brief cost report: {r.today.isoformat()} ({day}; period: {period})",
        "",
        f"{'Actual spend':<23} {_inr(r.actual_total_inr)}",
        f"  API: {'LLM':<16} {_inr(r.usage_inr['llm'])}",
        f"  API: {'voice':<16} {_inr(r.usage_inr['tts'])}",
    ]
    for cat, amount in r.cash_inr.items():
        lines.append(f"  cash: {cat:<15} {_inr(amount)}")
    lines += ["", "Caps by period (USD)  LLM spent/cap    voice spent/cap"]
    for p, llm, tts in r.periods:
        lines.append(
            f"  {p.id:<19} ${llm:6.2f}/${p.llm_cap_usd:6.2f}   ${tts:6.2f}/${p.tts_cap_usd:6.2f}"
        )
    lines += [
        "",
        f"Projected max       {_inr(r.projected_max_inr)}  "
        f"(actual + remaining caps {_inr(r.remaining_caps_inr)} "
        f"+ planned fixed items {_inr(r.planned_remaining_inr)})",
        f"Ceiling             {_inr(r.ceiling_inr)}",
        f"Headroom            {_inr(r.headroom_inr)}",
        "Optional spend      "
        + (
            "FROZEN (actual spend passed "
            f"{_inr(r.freeze_threshold_inr)} before Day {r.freeze_before_day})"
            if r.frozen
            else f"allowed up to {_inr(r.optional_allowed_up_to_inr)} (spending rule 1)"
        ),
    ]
    if r.headroom_inr < 0:
        lines.append("WARNING: projected max exceeds the ceiling; reduce caps or planned spend.")
    lines += [f"Note: {n}" for n in r.notes]
    return "\n".join(lines)
