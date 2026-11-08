"""Command-line entry point: `brief`."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from brief import __version__
from brief.budget import (
    DEFAULT_CASH,
    DEFAULT_CONFIG,
    DEFAULT_USAGE,
    IST,
    Budget,
    BudgetConfigError,
    load_config,
    render_report,
)
from brief.doctor import render, run_checks
from brief.edition.checks import STAGES, load_edition, validate_file
from brief.edition.schema import json_schema_text
from brief.linkcheck import check_links, collect_links, render_linkcheck

SCHEMA_PATH = Path("schemas/edition.schema.json")

app = typer.Typer(help="AI Daily Brief toolkit.", no_args_is_help=True, add_completion=False)
schema_app = typer.Typer(help="Edition JSON Schema.", no_args_is_help=True)
cost_app = typer.Typer(help="Budget caps and the ₹15,000 ceiling.", no_args_is_help=True)
app.add_typer(schema_app, name="schema")
app.add_typer(cost_app, name="cost")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"brief {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """AI Daily Brief toolkit."""


@app.command()
def doctor() -> None:
    """Check required local tools: Python, ffmpeg/ffprobe, wrangler, gitleaks."""
    results = run_checks()
    typer.echo(render(results))
    if any(r.required and not r.ok for r in results):
        raise typer.Exit(code=1)


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(help="Edition JSON file.")],
    stage: Annotated[
        str, typer.Option(help="How complete the record must be: draft, review or published.")
    ] = "draft",
) -> None:
    """Run editorial checks C01, C03, C04, C06, C07, C09, C10, C11 on an edition."""
    if stage not in STAGES:
        raise typer.BadParameter(f"stage must be one of {', '.join(STAGES)}")
    report = validate_file(path, stage)
    typer.echo(report.render())
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def linkcheck(
    path: Annotated[Path, typer.Argument(help="Edition JSON file.")],
    workers: Annotated[int, typer.Option(min=1, max=16)] = 8,
) -> None:
    """Check C02: every source and evidence link returns HTTP 200 (makes web requests)."""
    edition, issues = load_edition(path)
    if edition is None:
        for issue in issues:
            typer.echo(f"{issue.code}: {issue.message}")
        raise typer.Exit(code=2)
    results = check_links(collect_links(edition), workers=workers)
    typer.echo(render_linkcheck(str(path), results))
    if not all(r.ok for r in results):
        raise typer.Exit(code=1)


@schema_app.command("export")
def schema_export(
    check: Annotated[
        bool, typer.Option(help="Only check that the committed schema is up to date.")
    ] = False,
    out: Annotated[Path, typer.Option(help="Where the schema file lives.")] = SCHEMA_PATH,
) -> None:
    """Write (or verify) schemas/edition.schema.json from the pydantic models."""
    text = json_schema_text()
    if check:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != text:
            typer.echo(f"{out} is out of date; run `brief schema export`.")
            raise typer.Exit(code=1)
        typer.echo(f"{out} is up to date.")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    typer.echo(f"wrote {out}")


@cost_app.command("report")
def cost_report(
    today: Annotated[
        str | None, typer.Option(help="Report date YYYY-MM-DD (default: today, IST).")
    ] = None,
    config: Annotated[Path, typer.Option()] = DEFAULT_CONFIG,
    usage: Annotated[Path, typer.Option()] = DEFAULT_USAGE,
    cash: Annotated[Path, typer.Option()] = DEFAULT_CASH,
) -> None:
    """Actual spend, caps per period, projected max and headroom under the ceiling."""
    try:
        budget = Budget(load_config(config), usage, cash)
        day = date.fromisoformat(today) if today else datetime.now(IST).date()
        report = budget.report(day)
    except (BudgetConfigError, ValueError) as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=2) from exc
    typer.echo(render_report(report))
    if report.headroom_inr < 0:
        raise typer.Exit(code=1)
