"""Command-line entry point: `brief`."""

from __future__ import annotations

import json
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
from brief.edition.caption import build_caption, caption_for_posting
from brief.edition.checks import STAGES, load_edition, validate_file
from brief.edition.schema import json_schema_text
from brief.experiment.errorlog import (
    ErrorLogIntegrityError,
    add_checkpoint,
    append_error,
    append_resolution,
    full_verify,
    init_anchor,
)
from brief.experiment.report import experiment_report, phase1_report
from brief.experiment.sampler import sample_story_ranks
from brief.linkcheck import check_links, collect_links, render_linkcheck
from brief.tts.config import (
    ALLOWED_VOICES,
    DEFAULT_TTS_CONFIG,
    TTSConfigError,
    load_tts_config,
    set_active_voice,
)

SCHEMA_PATH = Path("schemas/edition.schema.json")

app = typer.Typer(help="AI Daily Brief toolkit.", no_args_is_help=True, add_completion=False)
schema_app = typer.Typer(help="Edition JSON Schema.", no_args_is_help=True)
cost_app = typer.Typer(help="Budget caps and the ₹15,000 ceiling.", no_args_is_help=True)
app.add_typer(schema_app, name="schema")
app.add_typer(cost_app, name="cost")
report_app = typer.Typer(help="Phase 1 and experiment reports.", no_args_is_help=True)
experiment_app = typer.Typer(
    help="Experiment instruments: error log, audit sampler.", no_args_is_help=True
)
app.add_typer(report_app, name="report")
app.add_typer(experiment_app, name="experiment")
tts_app = typer.Typer(help="Narration voice (ADR-004).", no_args_is_help=True)
app.add_typer(tts_app, name="tts")
EXPERIMENT_DIR = Path("experiment")
EDITIONS_DIR = Path("editions")


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


@app.command()
def caption(
    path: Annotated[Path, typer.Argument(help="Edition JSON file.")],
    write: Annotated[bool, typer.Option(help="Store the caption in the edition file.")] = False,
    posting: Annotated[bool, typer.Option(help="Print the text to paste, with hashtags.")] = False,
) -> None:
    """Generate the caption from the edition record (same record, same caption)."""
    edition, issues = load_edition(path)
    if edition is None:
        for issue in issues:
            typer.echo(f"{issue.code}: {issue.message}")
        raise typer.Exit(code=2)
    text = build_caption(edition)
    if write:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["caption"] = text
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        edition = edition.model_copy(update={"caption": text})
    typer.echo(caption_for_posting(edition) if posting else text)


@report_app.command("phase1")
def report_phase1(
    editions: Annotated[Path, typer.Option(help="Editions directory.")] = EDITIONS_DIR,
) -> None:
    """Completion, H1 supply, H3 time, H6 stability, check counts and review counters."""
    typer.echo(phase1_report(editions), nl=False)


@report_app.command("experiment")
def report_experiment(
    experiment: Annotated[Path, typer.Option(help="Experiment directory.")] = EXPERIMENT_DIR,
    editions: Annotated[Path, typer.Option(help="Editions directory.")] = EDITIONS_DIR,
) -> None:
    """H2 accuracy, H4 usefulness, H5 distinctiveness, audit coverage (refuses a tampered log)."""
    result = experiment_report(experiment, editions)
    typer.echo(result.text, nl=False)
    if not result.integrity_ok:
        raise typer.Exit(code=1)


@experiment_app.command("log-error")
def experiment_log_error(
    issue_key: Annotated[str, typer.Option(help="e.g. ADB-2026-12-03")],
    source: Annotated[str, typer.Option(help="auditor, self, panel or founder")],
    severity: Annotated[str, typer.Option(help="critical, material, minor or process")],
    description: Annotated[str, typer.Option()],
    story_rank: Annotated[int | None, typer.Option(min=1, max=7)] = None,
    evidence_url: Annotated[str, typer.Option()] = "",
    caught_pre_publication: Annotated[bool, typer.Option()] = False,
    log: Annotated[Path, typer.Option()] = EXPERIMENT_DIR / "error-log.csv",
) -> None:
    """Append an error to the append-only error log."""
    try:
        entry = append_error(
            log,
            issue_key=issue_key,
            source=source,
            severity=severity,
            description=description,
            logged_at=datetime.now(IST),
            story_rank=story_rank,
            evidence_url=evidence_url,
            caught_pre_publication=caught_pre_publication,
        )
    except (ValueError, ErrorLogIntegrityError) as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"logged {entry}")


@experiment_app.command("resolve-error")
def experiment_resolve_error(
    refers_to: Annotated[str, typer.Option(help="Error entry id, e.g. E0003")],
    correction_ref: Annotated[str, typer.Option(help="Where the correction is recorded")],
    description: Annotated[str, typer.Option()],
    log: Annotated[Path, typer.Option()] = EXPERIMENT_DIR / "error-log.csv",
) -> None:
    """Record a correction as a new row; the original error row stays."""
    try:
        entry = append_resolution(
            log,
            refers_to=refers_to,
            correction_ref=correction_ref,
            description=description,
            logged_at=datetime.now(IST),
        )
    except (ValueError, ErrorLogIntegrityError) as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"logged {entry} (resolves {refers_to})")


@experiment_app.command("sample-audit")
def experiment_sample_audit(
    path: Annotated[Path, typer.Argument(help="Edition JSON file.")],
    k: Annotated[int, typer.Option(min=1, max=7)] = 2,
) -> None:
    """Which stories the auditor checks (seeded from the issue key; reproducible)."""
    edition, issues = load_edition(path)
    if edition is None:
        for issue in issues:
            typer.echo(f"{issue.code}: {issue.message}")
        raise typer.Exit(code=2)
    ranks = sample_story_ranks(edition.issue_key, [s.rank for s in edition.stories], k)
    typer.echo(f"{edition.issue_key}: audit stories {', '.join(map(str, ranks))}")


@experiment_app.command("init-log")
def experiment_init_log(
    log: Annotated[Path, typer.Option()] = EXPERIMENT_DIR / "error-log.csv",
) -> None:
    """Create the error log's random genesis anchor once, before the first entry."""
    try:
        anchor = init_anchor(log, datetime.now(IST))
    except ErrorLogIntegrityError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"anchor created (genesis {anchor.genesis[:12]}...); commit it now")


@experiment_app.command("checkpoint")
def experiment_checkpoint(
    log: Annotated[Path, typer.Option()] = EXPERIMENT_DIR / "error-log.csv",
) -> None:
    """Record the current row count and head hash in the anchor (then commit it)."""
    try:
        cp = add_checkpoint(log, datetime.now(IST))
    except ErrorLogIntegrityError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"checkpoint at row {cp['count']}; commit the anchor" if cp else "nothing new")


@experiment_app.command("verify-log")
def experiment_verify_log(
    log: Annotated[Path, typer.Option()] = EXPERIMENT_DIR / "error-log.csv",
) -> None:
    """Check the chain, the anchor (genesis + checkpoints) and the anchor's git history."""
    problems, warnings = full_verify(log)
    for w in warnings:
        typer.echo(f"warning: {w}")
    for p in problems:
        typer.echo(f"problem: {p}")
    typer.echo("error log intact" if not problems else "error log NOT intact")
    if problems:
        raise typer.Exit(code=1)


@tts_app.command("voice")
def tts_voice(
    set_: Annotated[
        str | None, typer.Option("--set", help=f"Switch to voice {'/'.join(ALLOWED_VOICES)}.")
    ] = None,
    config: Annotated[Path, typer.Option()] = DEFAULT_TTS_CONFIG,
) -> None:
    """Show the narration voice, or switch it between B, C and D."""
    try:
        if set_ is not None:
            set_active_voice(set_, config)
        cfg = load_tts_config(config)
    except TTSConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for letter, v in cfg.voices.items():
        mark = "*" if v is cfg.active else " "
        typer.echo(f"{mark} {letter}  {cfg.engine} {v.voice_id} (lang {v.lang_code})")
    typer.echo(f"active: {cfg.active.letter} ({cfg.active.voice_id}), device {cfg.device}, "
               "paid fallback off")  # fmt: skip
