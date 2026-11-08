# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Planning is signed off and the **preparation window has started** (2026-11-08). Done so far: Phase 0, plus P1-02 (edition models and schema), P1-03 (`brief validate`), P1-04 (safe fetcher and `brief linkcheck`) and P1-36 (budget caps and ceiling tracker). Commits are authored as Akash <akash265457k@gmail.com> (repo-local config) with no Claude attribution. The business plan PDF is git-ignored and must never be committed. Work proceeds task by task from `TASKS.md`. A task is `Done` only when its acceptance criteria are verified, and each phase ends with a gate review (`docs/gates/phase-N.md`). Don't build ahead of the current phase into production paths. Prototyping on a branch is fine.

Toolchain (P0-02/P0-03 done): Python 3.12 via `uv` (system Python 3.9 must not be used), Typer, pytest, ruff, mypy (strict); FFmpeg 9 and gitleaks via Homebrew; wrangler pinned in `package.json` (`npm ci`). Commands: `uv run brief --help`, `uv run brief doctor`, `uv run brief validate editions/<date>.json --stage draft|review|published`, `uv run brief linkcheck editions/<date>.json` (makes web requests), `uv run brief cost report`, `uv run brief schema export [--check]` (run after any change to `brief/edition/schema.py`; a test fails if the committed schema is stale), `uv run pytest`, `uv run pytest tests/test_doctor.py::test_wrangler_matches_pin`, `uv run ruff check . && uv run ruff format --check .`, `uv run mypy`. Dependency policy: Python packages resolve only versions published before `tool.uv.exclude-newer` (about a 14-day buffer); Node tools are pinned exactly. The secret-scanning hook is enabled with `git config core.hooksPath .githooks`.

## Read these first

| Doc | For |
|---|---|
| `docs/IMPLEMENTATION_STRATEGY.md` | Scope, discovery, cost model, execution order |
| `docs/SYSTEM_ARCHITECTURE.md` | Components, data flow, **state machines**, env vars |
| `docs/DATABASE_DESIGN.md` | Tables, constraints, duplicate guards, edition JSON |
| `docs/EDITORIAL_PIPELINE.md` | Source tiers, rubric, hard rules R01–R12, checks C01–C12, review policy |
| `docs/WORKFLOWS.md` | Job types, `brief` CLI, n8n workflows, Phase 1 manual runbook |
| `docs/IMPLEMENTATION_ROADMAP.md`, `TASKS.md` | Phases, gates, backlog |
| `docs/VALIDATION_EXPERIMENT.md` | Pre-registered Phase 1 experiment; its thresholds must not change after Day 1 |
| `docs/DECISION_REVIEW.md` | **Approved decisions and final planning sign-off (2026-11-07)**, including PD-01–PD-07; contradictions found and how they were resolved |
| `docs/gates/G1_DAY1_READINESS.md` | Mandatory checklist before experiment Day 1 |
| `docs/TECHNICAL_DECISIONS.md` | ADRs and the **conflict register** |
| `docs/RISKS_AND_OPERATIONS.md` | Security, recovery runbooks, retention, facts to re-verify |

`AI_Daily_Brief_Business_Plan_Revised.pdf` is the business source of requirements (`pdftotext -layout` to read it). Where the docs above differ from it, the conflict register explains why.

## Architecture in one paragraph

All logic lives in one Python package, `brief` (CLI + job handlers). Postgres (Supabase) is the system of record, the `jobs` queue (`FOR UPDATE SKIP LOCKED`) and the `outbox_events` table. A Mac worker runs the heavy jobs (TTS, Pillow cards, FFmpeg render). n8n on a small VPS only schedules, shows editor forms and sends alerts, and it talks to the DB solely through `brief_*` SQL functions and `v_*` views. The static site is built by Python/Jinja and deployed to Cloudflare Pages. Media goes to R2: final MP4s are private and reach Meta through a presigned URL. LLM calls go through a router with tiers (`config/llm_routes.yaml`): a local Ollama model for tagging and same-event checks, Haiku for triage, and Sonnet for claims, script and second-pass verification, all under hard budget caps. Opus is for evaluation only and never in production routing. TTS is self-hosted (Kokoro primary, Piper alternative, provisional) behind the `TTSProvider` interface with a hash cache; a paid API is only an optional fallback. Phase 1 uses `editions/YYYY-MM-DD.json` files, not the DB.

## Decisions that override the business plan

These are the founder's **approved** decisions of 2026-11-07 (`docs/DECISION_REVIEW.md` §0). Details are in `docs/TECHNICAL_DECISIONS.md`.
- **Python core, thin n8n** (ADR-001). Never put editorial or publishing logic in n8n nodes.
- **Hybrid LLM routing** (ADR-003, approved): local Ollama for tagging and duplicates, kept only while it passes measured benchmarks and falling back to Haiku on failure or invalid output; Haiku for ranking suggestions; Sonnet for claims, script and second-pass verification; Opus for evaluation only. Caps are per plan window (`config/budget_periods.yaml`): $10 for Days 1–30, $20 for Days 31–60, $35 for Days 61–90; voice $10 per window. All caps sit under the ₹15,000 ceiling (pre-Day-1 spend included) and are enforced by the budget ladder. Model IDs are config. A fallback vendor is for outages only.
- **Self-hosted TTS** (ADR-004, 2026-11-08): Kokoro primary, Piper `en_GB-cori-medium` alternative, both provisional until the P1-05 benchmark. The pipeline only talks to the `TTSProvider` interface. A paid API is an optional fallback, off by default. Never use a voice without a commercial-use licence record (F5-TTS and VoiceStudio's default weights are non-commercial).
- **Preview before public** (ADR-012): preview deploy → human approval → production deploy (`site_live`) → Reel.
- **Cutoff 17:00 IST**, publish at 20:00 IST (ADR-005), on `PUBLISH_DAYS` = Mon–Fri. The **public soft launch at 5 editions a week** starts only after the validation experiment passes (ADR-017); 7 a week is reconsidered only at the Day-90 review. Monday may include important weekend stories: rubric v1.1 scores freshness against the edition window, using the event date, which is always kept separate from the publication date.
- **First-90-day cash ceiling ₹15,000**; founder time is costed at ₹500/h (`docs/IMPLEMENTATION_STRATEGY.md` §6).

## Invariants that should shape the code

- **Apify use:** use the MCP server only for interactive Actor research. Production calls allow-listed Actor IDs through the REST API, with fixed input, `maxItems` and per-run cost caps. An LLM never chooses tools or URLs.
- **Scraped text is untrusted.** Wrap it as delimited data, give the LLM no tools and no secrets, require schema-validated output, and check that every returned URL and excerpt exists in the inputs. Fetchers allow only https, block private IPs, and enforce size and time limits.
- **Every material claim needs evidence:** tier 1, or an attributed tier 2 source (`claims` + `evidence_records`). Discovery-only (tier 3) sources never establish a claim. Models must never produce citation URLs. `published_at`, `event_at` and `collected_at` stay separate.
- **Malformed LLM JSON is rejected,** with at most one bounded repair attempt, after which the job fails and the editor writes the copy. It never reaches rendering.
- **The pipeline may publish fewer stories, publish web-only, or skip a day.** Never pad an edition.
- **State machines** (story, issue, publishing job, job) are defined in `docs/SYSTEM_ARCHITECTURE.md` §6. They are enforced in `brief/db/state.py` **and** by SQL triggers. Transitions use `UPDATE … WHERE status = :expected`, and every transition writes `audit_logs` (plus `outbox_events` where needed) in the same transaction.
- **Idempotency everywhere:** `jobs.idempotency_key`, `candidate_stories.url_hash`, `daily_issues.issue_date`, `reels.render_hash`, `media_assets.cache_key`.
- **Instagram publishing:** `publishing_jobs` has a partial unique index on (issue, platform), `publish_reel` has `max_attempts = 1`, and the flow is container → poll status → `media_publish`. On any ambiguous outcome, set `needs_reconciliation` and run `reconcile_reel` (match the container status or the `issue_key` in a recent caption). **Never re-publish blindly.**
- **Official APIs only:** no passwords, cookies or session tokens to imitate a human. The IG token is stored encrypted (`platform_tokens`) and never logged. Secrets come from env or `.env` (git-ignored) and never go into job payloads, outbox events, audit details or n8n exports.
- **Corrections append, never overwrite** (`corrections`, `editorial_reviews` and `audit_logs` are append-only).
- **Human review:** automation prepares, humans approve. Every edition needs a human `final_approval` before `approved`, and a missing approval never leads to publication (no time-out publishing). Full claim-by-claim review applies to the first 30 manual and the first 30 automated editions (`daily_issues.production_epoch`), to the next 10 editions after any material factual error, and to any edition with contested, policy or safety stories. The approval view shows flagged claims, uncertain sources and failed checks first.
- **Mandatory audit trail** (`docs/EDITORIAL_PIPELINE.md` §14): every edition keeps source URLs, publisher and source type, published, event and collected timestamps, material claims with evidence and verification status, score and rationale, reviewer decisions and corrections, the final script and caption, media references, the deployment record, and the Instagram ID or permalink with its time. A missing item fails C01. *Discovered* is never the same as *verified*.
- **Error logs are append-only:** a corrected error stays recorded and still counts.
- **Budgets:** check `usage_ledger` before every paid LLM, TTS or Apify call. A blocked call is logged, never silently skipped.
- **Prompt or model changes** must pass the LLM regression set (`tests/llm_regression/`, task P3-12) before reaching production. Prompts are versioned files under `brief/llm/prompts/`.
- **Verify live docs before implementing:** Meta API shapes and limits, vendor pricing, licences and free-tier limits change. `docs/RISKS_AND_OPERATIONS.md` §2 lists the facts still to verify. Record the verified value and date in the relevant ADR.
