"""P1-36: budget periods, caps, the ₹15,000 ceiling and the optional-spend freeze."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brief.budget import (
    IST,
    Budget,
    BudgetExceededError,
    UsageEntry,
    load_config,
    render_report,
)
from brief.cli import app
from tests.conftest import ROOT

CONFIG = ROOT / "config" / "budget_periods.yaml"
DAY1 = date(2026, 12, 1)


def make_budget(tmp_path: Path, day1: date | None = DAY1) -> Budget:
    config = dataclasses.replace(load_config(CONFIG), day1=day1)
    cash = tmp_path / "cash.csv"
    cash.write_text("date,category,item,amount_inr,note\n", encoding="utf-8")
    return Budget(config, tmp_path / "usage.jsonl", cash)


def at(d: str, hm: str = "12:00") -> datetime:
    return datetime.fromisoformat(f"{d}T{hm}:00").replace(tzinfo=IST)


def spend(b: Budget, when: datetime, usd: float, category: str = "llm") -> None:
    b.record(
        UsageEntry(
            at=when,
            category=category,
            provider="p",
            operation="op",  # type: ignore[arg-type]
            cost_usd=usd,
        )
    )


def test_committed_config_matches_approved_caps() -> None:
    cfg = load_config(CONFIG)
    caps = {p.id: (p.llm_cap_usd, p.tts_cap_usd) for p in cfg.periods}
    assert caps == {
        "preparation": (7, 8),
        "days_1_30": (10, 10),
        "days_31_60": (20, 10),
        "days_61_90": (35, 10),
    }
    assert (cfg.ceiling_inr, cfg.freeze_threshold_inr, cfg.freeze_before_day) == (15000, 10000, 60)
    assert cfg.day1 is None and cfg.inr_per_usd == 88


def test_worst_case_projection_is_within_ceiling(tmp_path: Path) -> None:
    report = make_budget(tmp_path, day1=None).report(date(2026, 11, 8))
    assert report.projected_max_inr == pytest.approx(13_380)
    assert report.headroom_inr == pytest.approx(1_620)
    assert not report.frozen


@pytest.mark.parametrize(
    ("day", "period"),
    [
        (date(2026, 11, 30), "preparation"),
        (date(2026, 12, 1), "days_1_30"),
        (date(2026, 12, 30), "days_1_30"),
        (date(2026, 12, 31), "days_31_60"),
        (date(2027, 1, 29), "days_31_60"),
        (date(2027, 1, 30), "days_61_90"),
        (date(2027, 2, 28), "days_61_90"),
    ],
)
def test_period_mapping(tmp_path: Path, day: date, period: str) -> None:
    found = make_budget(tmp_path).period_for(day)
    assert found is not None and found.id == period


def test_after_day_90_has_no_period_and_blocks(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    assert b.period_for(date(2027, 3, 1)) is None
    with pytest.raises(BudgetExceededError, match="outside"):
        b.check("llm", 0.01, at("2027-03-01"))


def test_interim_cap_applies_only_to_days_31_60(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    for i in range(7):  # $9.10 spread over days 1-7 (stays under the $1.50 daily cap)
        spend(b, at(f"2026-12-0{i + 1}"), 1.30)
    with pytest.raises(BudgetExceededError, match="days_1_30"):
        b.check("llm", 1.00, at("2026-12-08"))  # 9.10 + 1.00 > $10
    b.check("llm", 1.00, at("2026-12-31"))  # Day 31: new period, $20 cap


def test_daily_llm_cap(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    spend(b, at("2026-12-02", "09:00"), 1.20)
    with pytest.raises(BudgetExceededError, match="daily"):
        b.check("llm", 0.40, at("2026-12-02", "18:00"))
    b.check("llm", 0.40, at("2026-12-03", "09:00"))


def test_preparation_has_its_own_daily_cap(tmp_path: Path) -> None:
    """Founder approval 2026-11-13: $3.00/day during preparation only; Day 1+ stay at $1.50."""
    b = make_budget(tmp_path)
    prep = at("2026-11-20", "09:00")  # before Day 1
    spend(b, prep, 2.50)
    b.check("llm", 0.40, at("2026-11-20", "18:00"))  # 2.90 <= 3.00
    with pytest.raises(BudgetExceededError, match=r"daily LLM cap is \$3\.00"):
        b.check("llm", 0.60, at("2026-11-20", "19:00"))
    spend(b, at("2026-12-02", "09:00"), 1.20)  # Day 1+: back to $1.50
    with pytest.raises(BudgetExceededError, match=r"daily LLM cap is \$1\.50"):
        b.check("llm", 0.40, at("2026-12-02", "18:00"))


def test_voice_cap_is_separate_from_llm(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    spend(b, at("2026-12-02"), 9.50, "tts")
    with pytest.raises(BudgetExceededError, match="tts cap"):
        b.check("tts", 1.00, at("2026-12-03"))
    b.check("llm", 1.00, at("2026-12-03"))


def test_blocked_call_is_logged_not_silently_skipped(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    with pytest.raises(BudgetExceededError):
        b.check("llm", 50.0, at("2026-12-02"), provider="anthropic", operation="draft_script")
    entry = b.usage()[-1]
    assert entry.status == "blocked_by_budget" and entry.cost_usd == 0
    assert entry.operation == "draft_script"


def test_preparation_spend_counts_inside_ceiling_once(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    spend(b, at("2026-11-20"), 5.00)  # bake-off, before Day 1
    report = b.report(date(2026, 11, 25))
    assert report.actual_total_inr == pytest.approx(440)
    # spent part moves from "remaining cap" to "actual": the projection is unchanged
    assert report.projected_max_inr == pytest.approx(13_380)
    llm_by_period = {p.id: llm for p, llm, _ in report.periods}
    assert llm_by_period == {
        "preparation": 5.0,
        "days_1_30": 0.0,
        "days_31_60": 0.0,
        "days_61_90": 0.0,
    }


def test_ended_periods_release_unspent_caps(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    report = b.report(date(2027, 1, 14))  # Day 45: preparation and Days 1-30 have ended
    released = (7 + 8 + 10 + 10) * 88
    assert report.projected_max_inr == pytest.approx(13_380 - released)


def test_planned_items_and_cash_ledger(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    with b.cash_path.open("a", encoding="utf-8") as fh:
        fh.write("2026-11-28,one_time,domain,1500,year 1\n")
    report = b.report(date(2026, 11, 29))
    assert report.cash_inr["one_time"] == 1500
    # domain spent 1,500 of its 2,500 planned max: projection falls by the unspent 1,000
    assert report.projected_max_inr == pytest.approx(13_380 - 1_000)


def test_freeze_only_counts_spend_before_day_60(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    with b.cash_path.open("a", encoding="utf-8") as fh:
        fh.write("2027-01-31,optional,designer,10500,after day 60\n")
    assert not b.report(date(2027, 2, 1)).frozen
    with b.cash_path.open("a", encoding="utf-8") as fh:
        fh.write("2027-01-10,optional,designer,10500,before day 60\n")
    report = b.report(date(2027, 2, 1))
    assert report.frozen and report.optional_allowed_up_to_inr == 0
    assert "FROZEN" in render_report(report)


def test_cli_cost_report(tmp_path: Path) -> None:
    b = make_budget(tmp_path, day1=None)
    result = CliRunner().invoke(
        app,
        [
            "cost",
            "report",
            "--today",
            "2026-11-08",
            "--config",
            str(CONFIG),
            "--usage",
            str(b.usage_path),
            "--cash",
            str(b.cash_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "₹13,380" in result.output and "₹15,000" in result.output


def test_recurring_item_keeps_unspent_allowance_reserved(tmp_path: Path) -> None:
    b = make_budget(tmp_path)
    with b.cash_path.open("a", encoding="utf-8") as fh:
        fh.write("2026-12-31,infrastructure,vps,450,month 1\n")
    report = b.report(date(2027, 1, 2))  # Day 33: preparation and Days 1-30 have ended
    released = (7 + 8 + 10 + 10) * 88
    # paid 450 of the 1,200 VPS allowance: 750 stays reserved, so the projection is unchanged
    assert report.projected_max_inr == pytest.approx(13_380 - released)
