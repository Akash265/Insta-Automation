"""Command-line entry point: `brief`."""

from __future__ import annotations

import typer

from brief import __version__
from brief.doctor import render, run_checks

app = typer.Typer(
    help="AI Daily Brief toolkit.",
    no_args_is_help=True,
    add_completion=False,
)


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
