"""Command-line entry point: `brief`."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from brief import __version__
from brief.budget import (
    DEFAULT_CASH,
    DEFAULT_CONFIG,
    DEFAULT_USAGE,
    IST,
    Budget,
    BudgetConfigError,
    BudgetExceededError,
    load_config,
    render_report,
)
from brief.doctor import render, run_checks
from brief.edition.caption import build_caption, caption_for_posting
from brief.edition.checks import STAGES, load_edition, validate_file
from brief.edition.schema import Edition, json_schema_text
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
from brief.media.cards import CardOverflowError, render_cards
from brief.media.render import RenderFailedError, render_reel
from brief.media.subtitles import build_subtitles
from brief.media.theme import DEFAULT_THEME, ThemeError, load_theme
from brief.site.build import SiteBuildError, build_site, load_site_config
from brief.site.deploy import DeployError, deploy_site, fetch_target, load_credentials
from brief.tts.base import TTSProviderError
from brief.tts.config import (
    ALLOWED_VOICES,
    DEFAULT_TTS_CONFIG,
    TTSConfigError,
    load_tts_config,
    set_active_voice,
)
from brief.tts.lexicon import LexiconError
from brief.tts.service import (
    NarrationFailedError,
    Segment,
    build_service,
    edition_segments,
    file_sha256,
    narration_refs,
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
site_app = typer.Typer(help="Static website (ADR-006).", no_args_is_help=True)
app.add_typer(site_app, name="site")
script_app = typer.Typer(help="Edition copy: optional LLM draft (P1-13).", no_args_is_help=True)
app.add_typer(script_app, name="script")
DEFAULT_SITE_CONFIG = Path("config/site.yaml")
SITE_TEMPLATES = Path("site_templates")
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


CONTENT_CHECKS = ("C03", "C04", "C06", "C07", "C09", "C10", "C11")


@script_app.command("draft")
def script_draft(
    path: Annotated[Path, typer.Argument(help="Edition JSON file (status draft).")],
    write: Annotated[bool, typer.Option(help="Store the draft in the edition file.")] = False,
    force: Annotated[
        bool, typer.Option(help="Replace an existing script (the editor's copy is lost).")
    ] = False,
    env_file: Annotated[Path, typer.Option(help="Where ANTHROPIC_API_KEY is.")] = Path(".env"),
) -> None:
    """Draft headline, summary, card, narration, hook and outro from supported claims.

    Paid call on the T6 route (config/llm_routes.yaml), under the budget caps; at most
    one repair. The editor reviews and edits every word before approval.
    """
    import os

    from brief.edition.checks import parse_edition, validate_edition
    from brief.llm.client import AnthropicJSON, LLMError, load_models
    from brief.llm.script_draft import (
        TASK,
        DraftError,
        apply_draft,
        draft_script,
        load_route,
        render_text,
    )
    from brief.site.deploy import read_dotenv

    edition, issues = load_edition(path)
    if edition is None:
        for issue in issues:
            typer.echo(f"{issue.code}: {issue.message}")
        raise typer.Exit(code=2)
    if edition.status != "draft":
        typer.echo(f"error: the edition is '{edition.status}'; only a draft can be redrafted")
        raise typer.Exit(code=2)
    if edition.script is not None and write and not force:
        typer.echo("error: the edition already has a script; pass --force to replace it")
        raise typer.Exit(code=2)
    key = read_dotenv(env_file).get("ANTHROPIC_API_KEY")
    if key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        typer.echo(f"error: ANTHROPIC_API_KEY is not set (environment or {env_file})")
        raise typer.Exit(code=2)
    models = load_models()
    budget = Budget(load_config(DEFAULT_CONFIG), DEFAULT_USAGE, DEFAULT_CASH)
    try:
        route = load_route(TASK, models)
        draft = draft_script(edition, AnthropicJSON(budget, models), route)
    except BudgetExceededError as exc:
        typer.echo(f"blocked by budget: {exc}; write the copy by hand")
        raise typer.Exit(code=1) from exc
    except (DraftError, LLMError) as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from exc
    raw = json.loads(path.read_text(encoding="utf-8"))
    updated = apply_draft(raw, draft)
    typer.echo(render_text(draft.data))
    typer.echo(
        f"\n{draft.model}, {draft.attempts} call(s), ${draft.cost_usd:.4f} for the accepted "
        "call (all calls are in the usage ledger)"
    )
    new_edition, parse_issues = parse_edition(updated)
    found = parse_issues
    if new_edition is not None:
        found = [i for i in validate_edition(new_edition, "draft").issues
                 if i.code in CONTENT_CHECKS]  # fmt: skip
    for i in found:
        where = f" (story {i.story_rank})" if i.story_rank else ""
        typer.echo(f"{i.code} {i.severity}: {i.message}{where}")
    if write:
        path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        typer.echo(f"wrote the draft to {path} (script version {updated['script']['version']})")
    if any(i.severity == "blocking" for i in found):
        raise typer.Exit(code=1)


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


_TTS_ERRORS = (TTSConfigError, TTSProviderError, NarrationFailedError, LexiconError)


@tts_app.command("fetch-model")
def tts_fetch_model(config: Annotated[Path, typer.Option()] = DEFAULT_TTS_CONFIG) -> None:
    """Download (once) and hash-check the pinned Kokoro files for voices B, C and D."""
    from brief.tts.kokoro import fetch_model

    try:
        paths = fetch_model(load_tts_config(config))
    except _TTS_ERRORS as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for name in paths:
        typer.echo(f"ok  {name} (sha256 matches)")


@tts_app.command("check")
def tts_check(config: Annotated[Path, typer.Option()] = DEFAULT_TTS_CONFIG) -> None:
    """Verify model hashes and load the engine offline (no audio is written)."""
    from brief.tts.kokoro import KokoroProvider

    try:
        cfg = load_tts_config(config)
        KokoroProvider(cfg).healthcheck()
    except _TTS_ERRORS as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"ok: {cfg.engine} {cfg.active.voice_id} (voice {cfg.active.letter}) "
               f"loads offline on {cfg.device}")  # fmt: skip


@tts_app.command("say")
def tts_say(
    text: Annotated[str, typer.Argument(help="Text to speak (the lexicon is applied).")],
    out: Annotated[Path, typer.Option(help="Copy the WAV here for listening.")] = Path(
        "cache/tts/say.wav"
    ),
    config: Annotated[Path, typer.Option()] = DEFAULT_TTS_CONFIG,
) -> None:
    """Synthesise one line with the active voice, to listen to a voice or a lexicon fix."""
    try:
        audio = build_service(load_tts_config(config)).narrate(Segment(0, text))
    except _TTS_ERRORS as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio.path.read_bytes())
    typer.echo(f"{out} ({audio.duration_s:.1f} s, voice {audio.voice.voice})")


@tts_app.command("synth")
def tts_synth(
    path: Annotated[Path, typer.Argument(help="Edition JSON file.")],
    write: Annotated[
        bool, typer.Option(help="Record the narration in the edition's media.narration.")
    ] = False,
    config: Annotated[Path, typer.Option()] = DEFAULT_TTS_CONFIG,
) -> None:
    """Narrate an edition: hook, one segment per story, outro. Unchanged text is cached."""
    try:
        edition, issues = load_edition(path)
        if edition is None:
            raise NarrationFailedError("; ".join(i.message for i in issues) or "invalid edition")
        service = build_service(load_tts_config(config))
        audio = service.narrate_all(edition_segments(edition))
    except _TTS_ERRORS as exc:
        typer.echo(f"error: {exc}", err=True)
        typer.echo("narration failed: skip the Reel and publish web-only", err=True)
        raise typer.Exit(1) from exc
    total = 0.0
    for n, a in enumerate(audio):
        total += a.duration_s
        state = "cached" if a.cached else "new"
        typer.echo(f"segment {n}: {a.duration_s:5.1f} s  {state:6}  {a.path}")
    typer.echo(f"total narration: {total:.1f} s, voice {audio[0].voice.voice}")
    if write:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("media", {})
        data["media"] = data["media"] or {}
        data["media"]["narration"] = narration_refs(audio)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        typer.echo(f"recorded {len(audio)} segments in {path}")


_RENDER_ERRORS = (*_TTS_ERRORS, RenderFailedError, CardOverflowError, ThemeError, ValueError)


def _edition_or_exit(path: Path) -> Edition:
    edition, issues = load_edition(path)
    if edition is None:
        typer.echo("error: " + "; ".join(i.message for i in issues), err=True)
        raise typer.Exit(1)
    return edition


@app.command("cards")
def cards_cmd(
    path: Annotated[Path, typer.Argument(help="Edition JSON file.")],
    out: Annotated[Path, typer.Option(help="Output folder.")] = Path("out"),
    theme: Annotated[Path, typer.Option()] = DEFAULT_THEME,
) -> None:
    """Draw the intro, story and outro cards (1080x1920 PNG) for review."""
    edition = _edition_or_exit(path)
    try:
        cards = render_cards(load_theme(theme), edition, out / edition.issue_key / "cards")
    except _RENDER_ERRORS as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for card in cards:
        typer.echo(f"{card.kind:5}  {card.path}")


@app.command("render")
def render_cmd(
    path: Annotated[Path, typer.Argument(help="Edition JSON file.")],
    write: Annotated[
        bool, typer.Option(help="Record narration, MP4 and cover in the edition.")
    ] = False,
    out: Annotated[Path, typer.Option(help="Output folder.")] = Path("out"),
    theme: Annotated[Path, typer.Option()] = DEFAULT_THEME,
    config: Annotated[Path, typer.Option()] = DEFAULT_TTS_CONFIG,
) -> None:
    """Narrate (cached), draw cards and subtitles, and render the checked Reel MP4."""
    edition = _edition_or_exit(path)
    target = out / edition.issue_key
    try:
        th = load_theme(theme)
        segments = edition_segments(edition)
        audio = build_service(load_tts_config(config)).narrate_all(segments)
        cards = render_cards(th, edition, target / "cards")

        def subtitles_for(timeline: list[tuple[float, float]]) -> list[Any]:
            spans = [(s.text, start, spoken)
                     for s, (start, spoken) in zip(segments, timeline, strict=True)]  # fmt: skip
            return build_subtitles(th, spans, target / "subs")

        result = render_reel(cards, [a.path for a in audio], subtitles_for, target,
                             edition.issue_key, (th.width, th.height, th.subtitle_top))  # fmt: skip
    except _RENDER_ERRORS as exc:
        typer.echo(f"error: {exc}", err=True)
        typer.echo("render failed: no Reel today; publish web-only", err=True)
        raise typer.Exit(1) from exc
    c = result.checks
    typer.echo(f"{result.mp4}  ({c.manifest['format_duration']} s, {c.integrated_lufs:.1f} LUFS, "
               f"true peak {c.true_peak_dbtp:.1f} dBTP, attempts {result.attempts}, "
               f"{result.seconds:.0f} s to render)")  # fmt: skip
    typer.echo(f"cover: {result.cover}\nreport: {result.report}")
    if write:
        data = json.loads(path.read_text(encoding="utf-8"))
        media = data.get("media") or {}
        media["narration"] = narration_refs(audio)
        media["mp4"] = {"key": f"reels/{edition.issue_key}.mp4", "sha256": file_sha256(result.mp4)}
        media["cover"] = {
            "key": f"covers/{edition.issue_key}.png",
            "sha256": file_sha256(result.cover),
        }
        data["media"] = media
        if data.get("experiment") is not None:
            data["experiment"]["render_attempts"] = result.attempts
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        typer.echo(f"recorded media in {path}")


@site_app.command("build")
def site_build(
    editions: Annotated[Path, typer.Option(help="Folder of YYYY-MM-DD.json editions.")] = Path(
        "editions"
    ),
    out: Annotated[Path, typer.Option(help="Output folder (replaced).")] = Path("dist"),
    preview: Annotated[
        bool, typer.Option(help="Also build in-review editions, marked as previews (noindex).")
    ] = False,
    config: Annotated[Path, typer.Option()] = DEFAULT_SITE_CONFIG,
    templates: Annotated[Path, typer.Option()] = SITE_TEMPLATES,
) -> None:
    """Build the static site (issues, /today, /archive, feeds) from edition records."""
    try:
        result = build_site(editions, out, load_site_config(config), templates, preview)
    except (SiteBuildError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for name, reason in result.skipped:
        typer.echo(f"skipped {name}: {reason}")
    kind = "preview" if result.preview else "production"
    typer.echo(f"built {len(result.issues)} issue(s), {len(result.files)} files into "
               f"{result.out} ({kind} build)")  # fmt: skip
    if result.latest:
        typer.echo(f"/today -> /issues/{result.latest}/")
    else:
        typer.echo("no publishable editions yet: /today is not built")


@site_app.command("deploy")
def site_deploy(
    preview: Annotated[
        bool, typer.Option("--preview", help="Deploy to the preview alias.")
    ] = False,
    production: Annotated[
        bool, typer.Option("--production", help="Deploy to production (approved build only).")
    ] = False,
    dist: Annotated[Path, typer.Option(help="Built site folder.")] = Path("dist"),
    record: Annotated[
        Path | None, typer.Option(help="Edition JSON to record the deployment in.")
    ] = None,
    env_file: Annotated[Path, typer.Option(help="Credentials file.")] = Path(".env"),
) -> None:
    """Upload dist/ to Cloudflare Pages (wrangler direct upload) and check the live site."""
    if preview == production:
        typer.echo("error: choose exactly one of --preview or --production", err=True)
        raise typer.Exit(2)
    try:
        creds = load_credentials(env_file)
        result = deploy_site(dist, production, creds, fetch_target(creds))
    except DeployError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{result.mode} deploy live at {result.site_url}")
    if result.deployment_url:
        typer.echo(f"this deployment: {result.deployment_url}")
    for check in result.checks:
        typer.echo(f"  ok  {check}")
    if record is not None:
        data = json.loads(record.read_text(encoding="utf-8"))
        deployment = data.get("deployment") or {}
        if production:
            deployment["production_deploy_id"] = result.deployment_url or result.site_url
            deployment["deployed_at"] = datetime.now(IST).isoformat(timespec="seconds")
        else:
            deployment["preview_url"] = result.site_url
        deployment.setdefault("linkcheck", "not_run")
        data["deployment"] = deployment
        record.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        typer.echo(f"recorded the deployment in {record}")
