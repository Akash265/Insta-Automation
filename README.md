# AI Daily Brief

A daily, source-linked AI-news brief: one reviewed edition record becomes a short Reel, a web issue page and (later) an email. Planning and decisions live in [`docs/`](docs/) and the backlog in [`TASKS.md`](TASKS.md). Start with [`docs/IMPLEMENTATION_STRATEGY.md`](docs/IMPLEMENTATION_STRATEGY.md).

**Status:** preparation window (Phase 0–1 toolkit). Nothing is published yet.

## Setup (macOS)

```sh
# 1. Tools (Homebrew)
brew install uv gitleaks ffmpeg

# 2. Python 3.12 and project dependencies (system Python 3.9 is not used)
uv python install 3.12
uv sync

# 3. Pinned Node tooling (wrangler for Cloudflare Pages)
npm ci

# 4. Secret scanning on every commit
git config core.hooksPath .githooks

# 5. Local configuration — never commit .env
cp .env.example .env

# 6. Check everything
uv run brief doctor
```

`brief doctor` exits non-zero if a required tool is missing or the wrangler version doesn't match its pin in `package.json`. A missing FFmpeg subtitle filter is reported as a warning only; the subtitle method is decided in task P1-08.

## Everyday commands

```sh
uv run brief --help                     # CLI
uv run brief validate editions/2026-12-01.json --stage draft   # editorial checks (draft|review|published)
uv run brief linkcheck editions/2026-12-01.json               # every source link must return HTTP 200 (uses the internet)
uv run brief cost report                                       # spend vs caps and the ₹15,000 ceiling
uv run brief caption editions/2026-12-01.json --write          # caption from the edition record
uv run brief report phase1                                     # completion, supply, time, stability
uv run brief report experiment                                 # accuracy, panel, distinctiveness, audits
uv run brief experiment log-error --help                       # append-only error log (never edit the CSV)
uv run brief experiment verify-log                             # chain, genesis, checkpoints, committed anchor
uv run brief tts voice [--set B|C|D]                           # narration voice (default C = Kokoro am_adam)
uv sync --extra tts                                            # install Kokoro (optional; PyTorch)
uv run --extra tts brief tts synth editions/2026-12-01.json --write   # narrate an edition (cached)
uv run --extra tts brief tts say "Qwen runs on CUDA"           # hear one line (lexicon applied)
uv run brief schema export --check                             # committed JSON Schema is current
uv run pytest                           # all tests
uv run pytest tests/test_doctor.py::test_wrangler_matches_pin   # one test
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

## Dependency policy

- Python packages resolve only versions published before `tool.uv.exclude-newer` in `pyproject.toml` (a ~14-day supply-chain buffer). Move it forward deliberately when upgrading.
- Node tooling is pinned exactly in `package.json` and locked in `package-lock.json`.
- Every new dependency needs a one-line justification in its change (see `docs/SYSTEM_ARCHITECTURE.md` §10).
