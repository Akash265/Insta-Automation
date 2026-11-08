# TASKS — AI Daily Brief implementation backlog

**Finalised and signed off 2026-11-07.** Approved decisions are in §B.1 and §B.2. **No task is Done.** Implementation does not start until the founder explicitly approves it.

**Conventions**
- **IDs:** `P<phase>-<nn>` for tasks (with a `U` suffix for the user half of a split task), `G#` for gates, `OD-`/`PD-` for decisions, `V-` for verification items.
- **Owner:** §A lists **user actions** (founder only). §E lists **engineering tasks**. Engineering never creates accounts, sends messages or makes product decisions on the founder's behalf.
- **Priority:** `Critical` (blocks a gate) · `High` · `Medium` · `Low`.
- **Status:** `Not Started` · `In Progress` · `Blocked (reason)` · `Done`. A task is `Done` only when its acceptance criteria are verified; written code alone does not count. Decisions use `Approved` / `Pending` / `Proposed` / `Open`.
- Every code task includes tests, passes `ruff` + `mypy` + `pytest`, and updates any doc it contradicts.

**Contents:** [A. User actions](#a-user-actions) · [B. Decisions](#b-decisions) · [C. Gates](#c-decision-gates-and-milestones) · [D. Full-review tracking](#d-full-review-tracking) · [E. Engineering tasks](#e-engineering-tasks) · [F. Verification tracker](#f-verification-tracker)

**Current blockers:** G1 needs the §A.0 and §A.1 user actions (panel, auditor, accounts, sign-offs) **and** the Phase 0–1 toolkit, including P1-36. Engineering can start P0-01–P0-03 and P1-02–P1-04 now, without any account.

---

## A. User actions

These are actions **only the founder can take**: decisions, accounts in the founder's name, recruitment, editorial work and sign-offs. Engineering never does them; no message is sent and no account is created on the founder's behalf. Every row has a due phase, its dependencies and completion criteria.

### A.0 ★ Start first: reader panel and independent auditor
These have the longest lead time, and four Day-1 gate items depend on them (M3–M6).

| ID | Priority | Action | Due phase | Depends on | Completion criteria | Status |
|---|---|---|---|---|---|---|
| P1-18 | **Critical** | **Recruit the reader panel.** Using the [recruitment kit](docs/VALIDATION_EXPERIMENT.md#5-reader-panel-recruitment-kit), list 14–15 candidates covering the mix, send the invitation personally (WhatsApp, LinkedIn or direct), run the 4 screening questions, confirm participants. Unpaid | Preparation, start Day −18, done by Day −5 | — | ≥ 8 (target 8–12) people confirmed who pass screening; the mix is recorded (codes only in the repo) | Not Started |
| P1-21 | **Critical** | **Build and test the feedback form**: daily D1–D6, Day 7/14 W1–W4, one 1–5 scale, panel-code dropdown, date | Preparation, by Day −5 | — | One test response reaches the sheet and exports to `experiment/panel-responses.csv` (G1 M4) | Not Started |
| P1-22 | High | **Onboard the panel**: send the follow-up message (start date, about 18:45 link time, form link, privacy note, how to leave); assign codes; keep the code-to-name mapping **outside the repo** | Preparation, by Day −2 | P1-18, P1-21 | Every confirmed panelist has a code and the schedule (G1 M3) | Not Started |
| P1-23 | **Critical** | **Recruit and brief the independent accuracy auditor**: someone not involved in scriptwriting; walk through the responsibilities, audit record and escalation (VALIDATION_EXPERIMENT §6); agree the escalation channel; record which days they are available | Preparation, by Day −5 | — | Auditor confirmed; availability calendar and escalation channel written down; self-audit plan for days without the auditor (G1 M5) | Not Started |
| P1-24 | High | **Practice audit**: the auditor checks one fixture edition with the audit record and sends one test escalation | Preparation, by Day −1 | P1-23, P1-19, P1-02 | At least one `audit-log.csv` row; one escalation sent and received (G1 M6) | Not Started |
| P1-40 | High | **TTS listening panel**: find ≥ 3 listeners (reader-panel volunteers are fine) for the P1-05 blind test; they rate each anonymised clip 1–5 for naturalness and note mispronunciations or artefacts (about 15 min each) | Preparation, by Day −8 | — | ≥ 3 listeners' ratings recorded in `research/tts-benchmark/results.md` | Not Started |

### A.1 Other preparation-window actions (before Day 1)
| ID | Priority | Action | Due phase | Depends on | Completion criteria | Status |
|---|---|---|---|---|---|---|
| P1-01 | **Critical** | **Approve the source list** (about 20 sources: feed or URL, terms and robots note, tier, category) and **choose the 2 comparison AI-news roundups** (discovery-only, for H5) | Preparation, by Day −7 | — | `sources.yaml` + `docs/EDITORIAL_CHARTER.md` approved; two roundups recorded (G1 M1, M2) | Not Started |
| P1-12U | **Critical** | **Create the Cloudflare account**, Pages project, R2 buckets (`brief-private`, `brief-public`) and least-privilege API tokens; tokens go in `.env` only | Preparation, by Day −10 | — | The engineer can deploy to `*.pages.dev` with the scoped token (G1 M13) | Not Started |
| P1-26 | High | **Create the Anthropic Console account** with a spend limit matching the budget periods ($7 for the preparation bake-off) | Preparation, by Day −12 | — | Key in `.env`; vendor spend limit set (G1 M18) | Not Started |
| P1-27 | Low | **Optional**: create a paid voice-vendor account with a spend limit, **only if** the paid TTS fallback is approved (no local engine passes P1-05, or by founder choice) | P1-05 result | Key in `.env`; limit within the $8 / $10 contingency caps | Only if needed | Not Started (optional) |
| P0-06 | Medium | **Create the private GitHub repo** (if OD-10 is accepted) and invite the engineer | Preparation, by Day −15 | OD-10 | Repo exists; access granted | Not Started |
| P1-37 | **Critical** | **Sign off rubric v1.1**: freshness against the edition window (PD-06); hard rules R01–R12; eligibility threshold 55, frozen for the experiment | Preparation, by Day −3 | — | Signed and dated entry in `docs/gates/phase-1.md` (G1 M7) | Not Started |
| P1-25 | **Critical** | **Sign off the pre-registered thresholds** (VALIDATION_EXPERIMENT §3, including PD-05 median ≤ 130); the engineer copies them unchanged into `docs/gates/phase-1.md` | Preparation, by Day 0 | P1-19, P1-37 | Signed and dated; unchanged from §3 (G1 M17) | Not Started |
| P1-31 | High | **Schedule the time blocks**: 16:00–18:45 IST on 14 evenings, 15 min each morning, the Day 7 checkpoint | Preparation, by Day 0 | — | In the calendar (G1 M16) | Not Started |
| P1-38 | **Critical** | **Run the Day-1 readiness check (G1)** with the [checklist](docs/gates/G1_DAY1_READINESS.md) | Preparation, Day 0 | All G1 M1–M18 tasks | All 18 mandatory items ticked and signed, **or** Day 1 moved with the failing items named | Not Started |
| P1-30 | High | Decide the pending items PD-01 to PD-07 | Preparation | — | All seven recorded in §B.2 | **Done (2026-11-07)** |

### A.2 Days 1–14 (validation experiment)
| ID | Priority | Action | Due phase | Depends on | Completion criteria | Status |
|---|---|---|---|---|---|---|
| P1-16 | **Critical** | **Run the experiment** exactly as pre-registered: daily workflow, panel links, next-morning audit intake, append-only error log | Experiment, Days 1–14 | G1 passed (P1-38) | 14 days run (or a documented early-pivot re-test); every §3 metric computable | Not Started |
| P1-32 | High | **Day 7 checkpoint (G2)**: compute metrics; format changes only | Experiment, Day 7 | P1-16 | Day 7 section in `docs/gates/phase-1.md` | Not Started |
| P1-17 | **Critical** | **Experiment gate (G3)**: apply VALIDATION_EXPERIMENT §8; continue / pivot / stop; report panel results without overstating them | Experiment, Day 14–15 | P1-16 | Decision and reasons recorded; error log complete and unedited | Not Started |

### A.3 Before the public soft launch (gate G4)
| ID | Priority | Action | Due phase | Depends on | Completion criteria | Status |
|---|---|---|---|---|---|---|
| P0-05 | High | **Decide the brand name, Instagram handle and domain** (OD-01): availability checks, basic trademark search, register the domain (counts inside the ₹15,000, PD-01). The working title is fine before Day 1 | Preparation or experiment, **by Day 15** | — | `docs/BRAND.md`; domain registered; handle reserved | Not Started |
| P1-15 | **Critical** | **Create the Instagram Professional account**; agree the manual upload procedure and the Reel spec checklist | Experiment, by Day 15 | P0-05 | `docs/runbooks/manual-publish.md`; one private test upload | Not Started |
| P1-20U | **Critical** | **Write and approve the policy page content**: about, editorial standards, corrections policy, privacy (no personal data collected; cookieless analytics), contact | Experiment, by Day 14 | P0-05 | Texts approved for P1-20 | Not Started |
| P1-33 | **Critical** | **Soft-launch readiness check (G4)**: G3 = continue; brand and domain live; policy pages live; Instagram account ready; `noindex` removed | Day 15 | P1-17, P0-05, P1-15, P1-20, P1-20U | G4 recorded as passed in §C | Not Started |

### A.4 Days 15–90 (soft launch, automation, reliability)
| ID | Priority | Action | Due phase | Depends on | Completion criteria | Status |
|---|---|---|---|---|---|---|
| P1-34 | High | **Weekly review** (Mondays): time per edition, errors and corrections, audit coverage, audience feedback and metrics, cash vs the ₹15,000 ceiling (`brief cost report`), full-review counters (§D) | Soft launch → Day 90, weekly | G4 | A weekly note in `docs/reviews/`; spending rules applied | Not Started |
| P1-39 | Medium | **Voice-cap review (PD-07)**: once local TTS has worked in production, compare measured voice spend (expected ₹0) with the $10 contingency cap; decide whether to keep $10, move to $5, or set $0 if no paid fallback is wanted | Days 31–60 (after ≥ 4 weeks of measured usage) | P1-36, P1-05 | Decision recorded with measured monthly usage | Not Started |
| P1-35 | High | **Day 45 spend review**: actual vs model; apply spending rule 1 to any optional item; check the ₹10,000-before-Day-60 freeze | Automation window, Day 45 | P1-34, P1-36 | Decision recorded | Not Started |
| P2-01U | High | **Create the Supabase project** (Free plan, OD-04 proposed) | Soft launch, by Day 30 | OD-04 | Connection details to the engineer (in `.env` only) | Not Started |
| P2-12U | High | **Buy the VPS** (OD-05) after checking the price on the provider's site (V-13); log it in the cash ledger | Soft launch, by Day 30 | OD-05 | VPS exists; access shared securely; cost logged | Not Started |
| P2-13U | Medium | **Create the healthchecks.io account and the Telegram alert bot** (V-14) | Automation window, by Day 35 | — | Ping URLs and bot token in `.env` | Not Started |
| P4-07 | **Critical** | **90-day decision review (G9)**: reliability, editorial quality (error log, audit coverage), audience signals, cash and fully loaded cost, partial automated-epoch evidence; **decide PD-04 (7 a week?)** | Day 90 | G6 or a documented slip | `docs/reviews/day-90.md` with a continue / adjust / pause decision and the cadence decision | Not Started |

### A.5 After Day 90 (listed for completeness)
| ID | Priority | Action | Due phase | Depends on | Completion criteria | Status |
|---|---|---|---|---|---|---|
| P5-06 | High | Policy pages v2 (extends P1-20U): archive and corrections listing; privacy update ahead of email | Phase 5 | P5-01 | Texts approved | Not Started |
| P6-02U | **Critical** | **Meta developer account**, app and Instagram Login permissions (OD-07) | Phase 6 | P6-01, P1-15 | The engineer can create a test container | Not Started |
| P7-02 | **Critical** | Privacy notice update + consent wording + DPDP applicability check (OD-09) | Phase 7 | P7-01 | Reviewed and published before signup goes live | Not Started |
| P8-01 | High | Media kit from real metrics (no projections presented as fact) | Phase 8 | P7-07 | Every number sourced from recorded metrics | Not Started |
| P8-03 | Medium | Sponsor register + editorial independence page | Phase 8 | P8-02 | Published independence statement | Not Started |
| P8-05 | Low | Premium weekly analysis: 10 reader interviews; no build | Phase 8 | P7-07 | Findings recorded | Not Started |

## B. Decisions

### B.1 Approved decisions (founder, 2026-11-07)
| ID | Decision | Approved value | Status |
|---|---|---|---|
| OD-08 | First-90-day cash ceiling | **₹15,000** | **Approved** |
| OD-13 | Public soft launch | **5 editions a week**, only if the validation experiment passes (target Day 15, gate G4) | **Approved** |
| OD-03 | LLM architecture | **Hybrid:** local Ollama (tagging, duplicates; Haiku fallback) + Haiku 5.5 (ranking suggestions) + Sonnet 5.5 (claims, script, second-pass verification); **Opus for evaluation only**; $35/month cap with graduated controls; local tier kept only while it passes measured benchmarks | **Approved** |
| OD-16 | Experiment thresholds | As pre-registered in VALIDATION_EXPERIMENT §3, fixed before Day 1; Day 7 may change format only | **Approved** |
| OD-17 | Full-review periods | First **30 manual** and first **30 automated** editions in full claim-by-claim review | **Approved** |
| OD-18 | Material-error response | Any material factual error → **the next 10 editions in full review** | **Approved** |
| OD-19 | Human approval | Mandatory before every publication in the MVP; no silent or time-out publishing | **Approved** |
| OD-12 | Founder hourly value | **₹500/h** | **Approved** |
| OD-14 | Reader panel | 8–12 participants, **unpaid**; the founder recruits using the kit | **Approved** |
| OD-15 | Accuracy auditor | Independent **volunteer** recruited by the founder; not assumed available every day | **Approved** |
| OD-06 | Cutoff / publish | **17:00 / 20:00 IST** (on publishing days) | **Approved** |
| OD-20 | Editorial audit trail | Mandatory 14-item trail for every edition (EDITORIAL_PIPELINE §14) | **Approved** (as a requirement of the finalisation brief) |

### B.2 Decisions approved at sign-off (2026-11-07)
| ID | Decision | Approved value | Status |
|---|---|---|---|
| PD-01 | Pre-Day-1 spend and the ceiling | All pre-Day-1 expenditure (about ₹900 expected) counts **inside** the ₹15,000 | **Approved** |
| PD-02 | LLM cap for Days 31–60 | **$20 interim**; $35 for Days 61–90; $10 for Days 1–30; all under ₹15,000 | **Approved** |
| PD-03 | First 30 manual editions | **Public editions only**; private prototypes and experiment drafts don't count | **Approved** |
| PD-04 | 7 editions a week? | Decided **at the Day-90 review** (P4-07); no change before then | **Approved** |
| PD-05 | Final-five-day time threshold | **Median ≤ 130 minutes** | **Approved** |
| PD-06 | Monday edition and weekend stories | Weekend developments may appear Monday; rubric v1.1 scores freshness against the edition window using the event date; event and publication dates shown separately; no penalty just for being published earlier | **Approved** |
| PD-07 | Voice cap | **$10/month** until the vendor comparison is done; $5 reconsidered after measured usage (P1-39) | **Approved** |

### B.3 Open decisions (proposed defaults; not needed before Day 1 unless noted)
| ID | Decision | Proposed default | Needed by | Status |
|---|---|---|---|---|
| OD-01 | Brand, handle, domain | Working title for the private experiment; final before G4 | P0-05 (Day 15) | Proposed |
| OD-02 | TTS engine | **Decided 2026-11-08: self-hosted**: Kokoro primary, Piper `en_GB-cori-medium` alternative, **provisional until P1-05**; paid API is an optional fallback only | P1-05 (preparation) | Approved (provisional engine) |
| OD-04 | Supabase Free → Pro | Free through Day 90 with own backups; Pro at the Phase 5 gate | P2-01U | Proposed |
| OD-05 | VPS | Hetzner entry plan *(price unverified, V-13)* | P2-12U | Proposed |
| OD-07 | Instagram Login vs Facebook Login | Instagram Login | P6-02U | Proposed |
| OD-09 | Privacy / DPDP advice for email | Before email signup | P7-02 | Proposed |
| OD-10 | Code hosting | Private repo on GitHub Free *(Actions allowance unverified, V-15)* | P0-06 | Proposed |
| OD-11 | Email provider | P7-01 evaluation | P7-03 | Open |

## C. Decision gates and milestones

Gates decide progress, not dates. A failed or slipped gate moves everything after it.

| Gate | Target | Criteria | Decides | Depends on | Status |
|---|---|---|---|---|---|
| G1 Day-1 readiness | Day 0 | [G1 checklist](docs/gates/G1_DAY1_READINESS.md): 18 mandatory items (M1–M18); optional O1–O6 don't block | Start the experiment | P1-38 (and every task listed in the checklist) | Not Started |
| G2 Day 7 checkpoint | Day 7 | VALIDATION_EXPERIMENT §7 | Format adjustments; early-pivot option | P1-32 | Not Started |
| G3 Experiment gate | Day 14–15 | VALIDATION_EXPERIMENT §8 | Continue / pivot (7-day re-test, max 2) / stop | P1-17 | Not Started |
| G3-R1, G3-R2 Pivot re-tests | +7 days each | Same thresholds, scaled | Continue / stop | Only if G3 = pivot | Not Started |
| G4 Soft-launch readiness | Day 15 | G3 = continue; brand and domain; policy pages; Instagram account; `noindex` off | First public edition | P1-33 | Not Started |
| M-45 Spend review | Day 45 | STRATEGY §6.7 spending rules | Optional spend; freeze check | P1-35 | Not Started |
| G5 Phase 2 gate | About Day 45–55 | ROADMAP Phase 2 exit (10 consecutive days of ingestion) | Candidate pool in daily use | P2-16 | Not Started |
| G6 Phase 3 gate | About Day 60–65 | ROADMAP Phase 3 exit (10 consecutive editions) | Automated claims and script allowed; **epoch 2 begins** | P3-13 | Not Started |
| G7 Phase 4 + deploy jobs | About Day 65–75 | P4-06 + P5-04 acceptance | Automated narration, render and deploy | P4-06, P5-04 | Not Started |
| G8 First automated edition | After G6 + G7 | Full review (FR-A 1/30) | — (milestone) | G6, G7 | Not Started |
| G9 90-day decision review | Day 90 | ROADMAP 90-day plan; partial automated evidence stated as partial | Continue / adjust / pause; **7 editions a week or not (PD-04)** | P4-07 | Not Started |

## D. Full-review tracking

Update at every weekly review (P1-34). Counters come from `brief report phase1` (P1-14) and, from Phase 3, from SQL (P3-15).

| Track | Rule | Counter | Started | Ends when | Status |
|---|---|---|---|---|---|
| EXP | 14 private experiment editions: all in full review; **not counted** toward FR-M (PD-03 approved) | 0 / 14 | — | Day 14 | Not Started |
| FR-M | First **30 manual public** editions (PD-03 approved: public only) | 0 / 30 | — | 30 manual public editions reviewed in full (expected about Day 57) | Not Started |
| FR-A | First **30 automated** editions (epoch 2) | 0 / 30 | — | 30 reviewed in full (**expected after Day 90**) | Not Started |
| FR-E | Next **10 editions after each material error** (runs in parallel; the later end wins) | No open windows | — | — | — |

**Error-triggered windows log** (append-only):
| Opened | Triggering error (error-log ref) | Editions covered | Closed |
|---|---|---|---|

## E. Engineering tasks

The user half of split tasks (P1-12U, P1-20U, P2-01U, P2-12U, P2-13U, P6-02U) is in §A.

### E.Phase 0 — Repository and technical discovery

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P0-01 | Critical | Initialise git; add `.gitignore` (`.env`, `.venv`, `dist/`, `out/`, `*.mp4`, `cache/`), `.env.example` (names from SYSTEM_ARCHITECTURE §9), gitleaks pre-commit hook | — | Repo with first commit | `git status` clean; a fake secret in a test file is blocked by the pre-commit hook | **Done (2026-11-08)**: first commit `5821b37` by Akash; gitleaks hook blocked a planted token and scanned the commit clean; the business plan PDF is git-ignored by founder decision |
| P0-02 | Critical | Create the `uv` project for Python 3.12: `pyproject.toml`, `brief/` package, Typer CLI entry `brief`, ruff, mypy (strict for `brief/`), pytest | P0-01 | Runnable `brief --help`, `brief --version` | `uv run brief --help` works; `uv run pytest` passes (smoke test); `uv run ruff check` and `mypy` clean | **Done (2026-11-08)**: uv + Python 3.12.16; Typer CLI; ruff, mypy strict and pytest (15 tests) all pass |
| P0-03 | High | Install and pin local tools (ffmpeg 9.0.x via Homebrew, wrangler via pinned npx version); add `brief doctor` to check tool versions | P0-02 | `brief doctor`, README "Setup" section | `brief doctor` reports ffmpeg, ffprobe, wrangler and Python versions and exits non-zero if any is missing | **Done (2026-11-08)**: ffmpeg/ffprobe 9.0.2, wrangler 4.152.0 (pinned; published ≥ 14 days ago), gitleaks 8.30.1; `brief doctor` exits 0; README Setup written. npm install scripts for esbuild/workerd are held back (re-check in P1-12) |
| P0-04 | Medium | GitHub remote + Actions CI (ruff, mypy, pytest); no secrets in CI | P0-02, OD-10 | `.github/workflows/ci.yml` | CI green on main; a failing test turns a PR red | Not Started |

### E.Phase 1 — Toolkit and validation experiment (preparation window + Days 1–14)

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P1-02 | Critical | Pydantic edition models (`brief/edition/schema.py`) covering **every audit-trail field** ([EDITORIAL_PIPELINE §14](docs/EDITORIAL_PIPELINE.md#14-mandatory-editorial-audit-trail)): sources with publisher, type and tier; published, event and collected timestamps; claims with evidence and verification status; score and rationale; `review` (regime, checklist, decision); `corrections`; final `script` and `caption`; `media`; `deployment`; `publication`; plus the `production_log` and `experiment` blocks ([VALIDATION_EXPERIMENT §9](docs/VALIDATION_EXPERIMENT.md#9-data-captured)). Generate `schemas/edition.schema.json`; 2 fixture editions (normal and quiet day) | P0-02 | Models, schema, `tests/fixtures/editions/` | Schema regenerates deterministically (`brief schema export` diff is empty in CI); fixtures validate; removing any audit-trail field makes validation fail (test) | **Done (2026-11-08)**: `brief/edition/schema.py` (all 14 audit-trail items); `schemas/edition.schema.json` (committed; `brief schema export --check` and a test confirm it matches); fixtures `normal.json`, `quiet_day.json` (weekend story, PD-06) and `editions/_template.json` validate against the models and the JSON Schema; a parametrised test shows removing each audit-trail item fails C01. CI determinism check waits for P0-04 |
| P1-03 | Critical | `brief validate`: checks C01 (schema **and** audit-trail completeness), C03, C04, C06, C07, C09, C10, C11, with blocking vs warning levels. The report lists **flagged claims, uncertain sources and failed checks first** (the Phase 1 approval report, EDITORIAL_PIPELINE §9.4) | P1-02 | `brief/edition/checks.py` + CLI | Each check has at least one passing and one failing fixture test; exit code is non-zero on any blocking failure; the report order is tested | **Done (2026-11-08)**: `brief validate --stage draft|review|published` with C01, C03, C04, C06, C07, C09, C10, C11; passing and failing tests for each check; report order (flagged claims → uncertain sources → blocking → warnings) tested; exit 1 on any blocking issue. C04 ignores calendar years (documented) |
| P1-04 | High | Safe HTTP fetcher (`brief/net.py`: https only, SSRF guard, size and time limits, redirects ≤5) + `brief linkcheck` (C02) | P0-02 | Fetcher + CLI | Tests cover private IPs being blocked, an oversized body being cut off, and redirect following; linkcheck lists every non-200 URL | **Done (2026-11-08)**: `brief/net.py` (https only, no credentials in URLs, public addresses only for every hop, ≤ 5 redirects, 15 s timeout, 2 MB cap) + `brief linkcheck` (lists every non-200 URL with where it is used; exit 1). Tests use a local server and fake DNS; one live run against reserved example.* domains behaved as expected. Residual DNS-rebinding risk documented in `net.py` |
| P1-05 | Critical | **Local TTS benchmark** ([ADR-004](docs/TECHNICAL_DECISIONS.md#adr-004)): install Kokoro and Piper locally (**needs your approval for the new packages and espeak-ng before it starts**). Run the **same ~180-word script (60–90 s) plus the 20-term AI pronunciation list** through Kokoro `af_heart`, `am_adam`, `bf_emma` and Piper `en_GB-cori-medium` on the M5. Measure every acceptance criterion: commercial licensing (hard gate), naturalness (blind, founder + ≥ 3 listeners, P1-40), pronunciation, generation time, audio quality, reliability. F5-TTS and VoiceStudio are excluded on licence grounds | P0-02, P1-40 | `research/tts-benchmark/` (`script.md`, `terms.txt`, `licences.md`, `results.md`; audio clips not committed); `config/tts.yaml` v1; ADR-004 updated | Every criterion measured for every candidate; primary and alternative recorded (or a documented "none passed" decision for the founder); V-09, V-23, V-24 updated with sources and dates | Not Started |
| P1-06 | Critical | **Provider-independent TTS**: `brief/tts/base.py` (`TTSProvider`, `VoiceSpec`, `LicenceRecord`, `NarrationAudio`), `service.py` (lexicon, cache, provider chain from `config/tts.yaml`, licence gate), providers for the engines that pass P1-05, and `brief tts synth`. The paid adapter is built **only if** the fallback is approved | P1-05, P1-02, P1-36 | `brief/tts/`, `config/tts.yaml`, `video_templates/lexicon.yaml` | Tests with a fake provider: switching provider in config needs no pipeline change; unchanged text makes 0 synthesis calls (cache hit); a provider without `commercial_use_ok` is refused; a paid provider is refused unless enabled **and** `Budget.check("tts")` passes; output contract (WAV, duration, sha256) holds | Not Started |
| P1-07 | Critical | Visual identity v1 and card templates in Pillow: intro, story, outro; OFL fonts with licence files; palette (working title until OD-01 is settled) | P0-02 | `brief/media/cards.py`, `video_templates/` | Golden PNG tests pass; text fits at the maximum lengths (C09) without overflow; licences recorded | Not Started |
| P1-08 | High | Subtitle generator from segment durations (**method open**: the standard Homebrew ffmpeg 9 has no `ass`/`subtitles` filter. Recommended: Pillow-rendered caption overlays, which need no extra dependency; alternative: `ffmpeg-full`. Decide here and update ADR-015), phrase chunking, safe area for the Reels UI | P1-06 | `brief/media/subtitles.py` | Unit tests for chunk timing (each chunk ≤ 2 lines, ≤ 42 chars per line); subtitles stay within the 1080×1920 safe area | Not Started |
| P1-09 | High | LLM bake-off (ADR-003): (a) T5/T6/T7 on 10 real stories, **Sonnet 5.5 vs Haiku 5.5, with Opus 5.5 as an evaluation baseline only**, scored with rules (URL subset, excerpt substring, claim-type accuracy, claim precision) plus editor rating; (b) T1/T2 local candidates (install Ollama; `gemma4:e4b`, `qwen2.5:7b`) vs Haiku, measuring quality, latency, memory fit and invalid-output rate; (c) **measure the actual token volumes** that replace the ADR-003 assumptions | P1-02, P1-26 | `research/llm-bakeoff.md`; `config/llm_routes.yaml` v1; ADR-003 assumptions updated | Per-model scores, measured tokens and cost per edition recorded; local candidate meets or misses each of the four retention criteria offline; V-04 and V-07 updated | Not Started |
| P1-10 | Critical | `brief render`: FFmpeg assembly (cards + motion + narration + burned subtitles), cover frame, ffprobe validation report, render-time log | P1-06, P1-07, P1-08 | `brief/media/render.py`, `probe.py` | Fixture edition renders to 1080×1920, 30 fps, H.264/AAC, 35–90 s, audio/video length difference under 100 ms, loudness −14 ±1 LUFS; 3 consecutive renders give identical ffprobe manifests | Not Started |
| P1-11 | Critical | Site templates + `brief site build` from `editions/`: issue page, `/today`, `/archive`, policy page stubs, `sitemap.xml`, `feed.xml`, `search-index.json` | P1-02 | `brief/site/`, `site_templates/`, `dist/` | Build from fixtures creates every listed path; each story shows publisher, dates and a "Read original" link; HTML validates; mobile layout checked at 375 px | Not Started |
| P1-12 | Critical | Deploy tooling: `brief site deploy --preview/--production` against the Pages project; R2 upload helpers; verify the Pages and R2 free-tier limits on the official pages (V-11) | P1-11, P1-12U | `brief/site/deploy.py`; V-11 updated | Preview and production deploys work from the CLI on `*.pages.dev`; `/today` resolves to the latest issue; token scopes confirmed least-privilege | Not Started |
| P1-13 | High | **`brief caption` (mandatory for G1 M10):** the caption is generated from the same edition record and passes C09/C10. **`brief script draft` (optional):** LLM structured output, one bounded repair, the Days 1–30 $10 cap via P1-36; if used, used on all days or none | P1-03, P1-36; P1-09 and P1-26 for the draft | `brief/edition/caption.py`, `brief/llm/`, prompt `script.v1.md` | The caption is identical across reruns from the same record; the draft passes the schema or fails explicitly after 1 repair; unvalidated URLs fail C03; cost logged per call | Not Started |
| P1-14 | High | `brief report phase1`: average and median minutes per step, check failures, corrections, and **review-regime counts** (full vs exception; experiment vs manual-epoch editions) | P1-02 | CLI report | Runs over `editions/*.json` and prints H1, H3 and H6 and the FR-M counter (§D) | Not Started |
| P1-36 | **Critical** | **Budget periods + ceiling tracker:** `config/budget_periods.yaml` (Preparation LLM $7 / voice $8; Days 1–30 $10/$10; Days 31–60 $20/$10; Days 61–90 $35/$10; ceiling ₹15,000; freeze threshold ₹10,000 before Day 60); the cap check used by the LLM and TTS clients; `finance/cash-ledger.csv` for non-API cash (domain, VPS); `brief cost report` shows actual spend by category, projected max (actual + remaining caps) against ₹15,000, and the freeze status | P0-02 | `brief/budget.py`, `config/budget_periods.yaml`, CLI | Tests: a call over its period cap is blocked; Day-1–30 and Day-31–60 caps apply in the right windows; pre-Day-1 spend is included; the projected max is computed correctly on fixture data; no spend counted twice (G1 M18) | **Done (2026-11-08)**: `config/budget_periods.yaml` + `brief/budget.py` + `brief cost report`: caps per plan window (prep $7/$8; Days 1–30 $10/$10; 31–60 $20/$10; 61–90 $35/$10); $1.50 daily LLM cap; blocked calls logged; `finance/cash-ledger.csv` with one-off vs recurring planned items; freeze rule; projected max **₹13,380** (exact cap conversion) with ₹1,620 headroom. 17 tests |
| P1-19 | High | Experiment instruments: `experiment/` CSV templates (panel responses, audit log, **append-only error log**, coverage misses), the seeded audit sampler, `brief report experiment` (H2, H4, H5 with distributions and per-panelist medians, VALIDATION_EXPERIMENT §5.6) | P1-14 | Templates + CLI | A dry run on fixture data computes every metric in VALIDATION_EXPERIMENT §3; the report refuses to drop or edit error-log rows (test) | Not Started |
| P1-20 | High | Policy page templates (about, editorial standards, corrections policy, privacy with no personal data collected and cookieless analytics, contact) wired into the site; `noindex` removal switch | P1-11, P1-20U | `site_templates/pages/` | Pages render and are linked from the footer; `noindex` is off only in the soft-launch build | Not Started |

### E.Phase 2 — News ingestion automation

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P2-01 | Critical | Supabase project; roles `brief_app`, `brief_n8n`, `brief_backup`; SSL enforced; network restrictions; verify free-tier pause and backup facts | P1-17, P2-01U | ADR-002 facts verified | Each role connects with only its documented privileges (a test script tries forbidden operations and they fail) | Not Started |
| P2-02 | Critical | `brief db migrate` + `0001_init.sql` (all MVP tables from DATABASE_DESIGN §4, indexes, RLS, revokes, `allowed_transitions`) | P2-01 | `migrations/`, `brief/db/` | Migration applies cleanly to an empty local Postgres (Docker) and to Supabase; re-running is a no-op | Not Started |
| P2-03 | Critical | State-transition guards in Python + SQL triggers for `daily_issues`, `publishing_jobs`, `candidate_stories` | P2-02 | `brief/db/state.py` | Every allowed transition succeeds and every disallowed one raises an error, in both Python and SQL (table-driven tests) | Not Started |
| P2-04 | Critical | Job queue (enqueue, claim with SKIP LOCKED, lease renewal, complete, fail, backoff, dead) + `brief worker run` + heartbeat + `brief jobs list/retry/cancel/enqueue` | P2-02 | `brief/jobs/` | Concurrency test: 2 workers × 100 jobs, each job runs exactly once; an expired lease is reclaimed; `dead` emits an outbox event | Not Started |
| P2-05 | High | SQL interface for n8n: `brief_enqueue`, `brief_ensure_issue`, `brief_ack_event`, `v_sources_due`, `v_outbox_pending`, `v_watchdog` | P2-04 | `migrations/0002_n8n_interface.sql` | `brief_n8n` can call these and cannot touch tables directly (tested) | Not Started |
| P2-06 | High | `brief sources sync` from `sources.yaml` to the `sources` table | P2-02, P1-01 | CLI | Idempotent sync; removed sources are disabled, not deleted | Not Started |
| P2-07 | Critical | Ingest adapters: RSS/Atom, GitHub releases, arXiv (keyword and category filter, daily cap); conditional GET; canonical URL; date normalisation; `ingest_source` job handler + `brief ingest run` | P2-06, P1-04 | `brief/ingest/` | Recorded-cassette tests for each adapter; canonical-URL test table (≥25 cases); re-ingest inserts 0 duplicates | Not Started |
| P2-08 | High | Clustering + dedupe (content hash, shared primary link, trigram + entity) + `brief cluster run`; build a labelled evaluation set from Phase 1 data | P2-07 | `brief/intel/cluster.py`, `research/cluster-eval.md` | Measured duplicate recall ≥90% and false-merge rate ≤5% on the labelled set (otherwise thresholds are tuned or ADR-008 revisited) | Not Started |
| P2-09 | High | `brief issue import/export` for Phase 1 editions | P2-02, P1-02 | CLI | All Phase 1 editions import, and export → import → export is byte-identical | Not Started |
| P2-10 | Medium | Apify evaluation via MCP for any feedless tier-1 source (research only); if justified, `apify.py` adapter with allow-list, fixed input and per-run cap | P2-07 | `research/apify/`, optional adapter | Decision recorded; if an adapter is built, a non-allow-listed Actor ID is refused (test) and cost is logged per run | Not Started |
| P2-11 | High | Mac worker as a launchd service; `caffeinate` during 16:30–20:30; rotating file logs | P2-04 | `ops/launchd/*.plist`, runbook | The worker survives reboot and logout; its heartbeat is visible in `worker_heartbeats` | Not Started |
| P2-12 | High | VPS: Docker Compose (n8n pinned version, Caddy), firewall, Access/IP allow-list, `N8N_ENCRYPTION_KEY` backed up offline; n8n licence check | OD-05, P2-12U | `ops/vps/` | n8n reachable only over TLS by allowed users; the port scan shows only 22 and 443 | Not Started |
| P2-13 | High | n8n WF-01 (ingest scheduler), WF-09 (heartbeat + dead jobs), WF-10 (alert router to Telegram) + external dead-man's switch (healthchecks.io free plan; verify) pinged by the worker, n8n host and backup job | P2-05, P2-12, P2-13U | `n8n/WF-01.json`, `WF-09.json`, `WF-10.json` | Stopping the worker triggers an alert within 10 min; **stopping the VPS triggers an external alert**; a forced `dead` job triggers an alert; no credentials appear in the exported JSON | Not Started |
| P2-14 | Critical | Backups: `ops/backup.sh` container (`backup_db` job), WF-11, R2 lifecycle rules, weekly automated restore test | P2-02, P2-12 | Backups in `brief-private/backups/` | A restore into a scratch DB matches row counts; lifecycle rules are confirmed in the dashboard | Not Started |
| P2-15 | Medium | `brief maintenance prune` implementing the retention rules | P2-02 | CLI + job | Test data older than each retention limit is removed; protected (published) rows are kept | Not Started |
| P2-17 | High | Local LLM tier: Ollama as a launchd service on localhost, model pinned, unloaded after use (V-06), blocked during the render window; T1 tagging + T2 duplicate checks through the router with **automatic Haiku fallback on error, timeout (> 15 s) or invalid output** | P1-09, P2-08 | `brief/llm/providers/ollama.py`, `ops/launchd/ollama.plist` | Over the Phase 2 window, all four ADR-003 retention criteria are measured: quality (≥ 95% agreement; F1 within 5), latency (batch ≤ 10 min, p95 ≤ 5 s), reliability (failures + invalid ≤ 2%), cost (savings vs maintenance time). **If any fails, T1/T2 route to Haiku by config**, and the decision is recorded in ADR-003 | Not Started |
| P2-16 | Critical | Phase 2 gate review | P2-01…P2-15 | `docs/gates/phase-2.md` | 10 consecutive days of ingestion with no silent failures, and dedupe metrics recorded | Not Started |

### E.Phase 3 — Editorial intelligence

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P3-01 | Critical | LLM client + router per approved ADR-003: tiers from `config/llm_routes.yaml` (local / Haiku / Sonnet; **Opus allowed only in `evaluation` runs, never in production routes**), structured output, `stop_reason`/refusal handling, budget ladder via `usage_ledger` with **per-period caps from P1-36** ($1.50/day; $10 Days 1–30; $20 Days 31–60, PD-02; $35 Days 61–90; under the ₹15,000 ceiling), Message Batches for T4 daytime and T8, outage-only vendor fallback, prompt version files | P2-02, P1-09 | `brief/llm/` | Unit tests with a fake provider cover: over-budget blocked; a production route naming Opus is rejected at config load; refusal → `PermanentError`; outage → fallback; ledger written | Not Started |
| P3-02 | Critical | Hard rules R01–R12 (each at the stage where it applies) | P2-08 | `brief/intel/rules.py` | ≥2 fixture tests per rule; rule results stored in `rule_results` | Not Started |
| P3-03 | Critical | Scoring rubric **v1.1**: rule sub-scores, with freshness measured against the **edition window** using `event_at` (PD-06; Monday window Fri 17:00 → Mon 17:00), plus the triage prompt (LLM-proposed sub-scores with rationale) and editor override fields | P3-01, P3-02 | `brief/intel/score.py`, `prompts/triage.v1.md` | Each criterion records its origin; rule scores are deterministic; tests cover a Saturday event scored on Monday (gets 20), an old event in a new article (R03), unknown `event_at` (cap 8), and daily-cadence parity with v1.0 | Not Started |
| P3-04 | High | `prepare_shortlist` job + `brief shortlist build` + `v_shortlist` view; quiet-day flag | P3-03 | Job handler | On a replayed day of real data the shortlist contains no rejected or duplicate items and is ordered by score | Not Started |
| P3-05 | High | n8n WF-02 (cutoff, on `PUBLISH_DAYS` Mon–Fri at 17:00), WF-00 (outbox poller), WF-03 (shortlist form) + `brief_record_selection` | P3-04, P2-13 | `n8n/WF-00.json`, `WF-02.json`, `WF-03.json` | End-to-end on staging: cutoff → form → selection stored → `prepare_issue` enqueued; no cutoff runs on Saturday or Sunday; invalid selections are rejected | Not Started |
| P3-06 | Critical | Claim extraction (`prompts/claims.v1.md`, `brief claims extract`) with URL-subset and excerpt-substring checks; evidence fetch + private snapshot | P3-01, P1-04 | `brief/claims/` | Fabricated URLs and excerpts in fake model output are dropped (test); evidence rows are linked to snapshots | Not Started |
| P3-07 | Critical | Verification rules (tier rules, two-source rule for high-impact claims, contested handling) + the SQL constraint trigger | P3-06 | `brief/claims/verify.py` | Table-driven tests cover each rule in EDITORIAL_PIPELINE §7.2; the DB rejects `supported` without qualifying evidence | Not Started |
| P3-08 | Critical | Script and copy generation from the DB (port of P1-13) + critic pass T7 (script vs verified claims) + checks C01–C12 run against DB records | P3-07, P1-13 | `brief/edition/assemble.py` | A generated script always passes the blocking checks or the issue goes to `held` with reasons | Not Started |
| P3-09 | High | `prepare_issue` job chain + `brief issue prepare` + `issue_held` / `issue_scripted` events + WF-04 notifications | P3-08, P3-05 | Handler + `n8n/WF-04.json` | Editor receives status messages; a failure leaves the issue `held` with a reason | Not Started |
| P3-10 | High | Prompt-injection heuristic + adversarial fixtures | P3-06 | `brief/intel/injection.py` | Fixtures containing injection phrases are flagged; flagged stories need manual review (cannot be auto-approved) | Not Started |
| P3-11 | Medium | `brief cost report` + WF-13 weekly report (cost and operations sections) | P3-01, P2-13 | CLI + `n8n/WF-13.json` | The report matches `usage_ledger` totals to the cent | Not Started |
| P3-12 | High | LLM regression golden set (20 frozen stories) + runner, required on any prompt or model change; quarterly **Opus evaluation comparison** (evaluation only; results go to the founder as a proposal if the ADR-003 threshold is met) | P3-06, P3-08 | `tests/llm_regression/` | The runner gives pass/fail with thresholds; documented as a PR requirement in CLAUDE.md | Not Started |
| P3-15 | High | Editor-time instrumentation: form open → submit durations per touchpoint, "review too fast" note, automatic return to full review for 10 editions after a material error, founder-minutes KPI in WF-13 | P3-05, P3-11 | SQL + `n8n/WF-13.json` | Weekly report shows minutes per touchpoint; a simulated material error flips the next 10 editions to full review (test) | Not Started |
| P3-13 | Critical | Phase 3 gate review | P3-01…P3-12 | `docs/gates/phase-3.md` | 10 consecutive days of prepared issues; 0 unsupported material claims reach review; editor edit time measured | Not Started |

### E.Phase 4 — Media production automation

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P4-01 | High | Move the TTS cache to `media_assets` + private R2; fallback provider and Kokoro path | P1-06, P2-02 | `brief/tts/cache.py` | Cache hits avoid API calls across machines; forcing a primary failure uses the fallback (test) | Not Started |
| P4-02 | Critical | `render_issue` job on the `heavy` queue: render_hash skip, upload MP4 to private R2, `reels` rows, `issue_rendered` event | P1-10, P2-04 | Handler | Identical inputs ⇒ no re-render; MP4 stored with its hash; issue moves to `rendered` | Not Started |
| P4-03 | Critical | Video validation spec v1 as code (resolution, fps, codecs, duration, loudness, A/V length, size limit, cover frame) | P1-10 | `brief/media/probe.py` | Every spec rule has a passing and a failing test; a failing render blocks `rendered` | Not Started |
| P4-04 | Medium | Template versioning + last-known-good fallback | P1-07 | `video_templates/VERSION` | A render records the template version; a broken template version falls back (test) | Not Started |
| P4-05 | High | Asset licence enforcement: render blocked if any asset lacks `license` | P4-02 | Check in render | A test asset without a licence fails the render with a clear error | Not Started |
| P4-06 | Critical | Phase 4 gate review | P4-01…P4-05 | `docs/gates/phase-4.md` | 10 consecutive automated renders with no manual fixes; render time p95 recorded | Not Started |

### E.Phase 5 — Website and archive

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P5-01 | Critical | Site built from the DB: frozen `edition_json` per issue; topic, company and source pages (only with ≥3 stories); archive filter JS over `search-index.json` | P1-11, P2-09 | `brief/site/build.py` | Filtering by date, topic, company and source works with JS; pages still render without JS; no page has fewer than 3 stories | Not Started |
| P5-02 | High | SEO: titles, meta descriptions, canonical tags, JSON-LD (NewsArticle, CollectionPage), sitemap, RSS, OG/cover images | P5-01 | Templates | Structured-data validator passes on a sample; no duplicate titles | Not Started |
| P5-03 | High | Corrections: page display, `brief correct`, WF-12 form, `brief_record_correction`, `rebuild_site` | P5-01 | CLI + `n8n/WF-12.json` | A correction shows a dated note; the original text is preserved in the DB; the rebuild deploys | Not Started |
| P5-04 | Critical | `deploy_preview` + `go_live` jobs with HTTP verification; `/today` redirect; preview alias | P5-01, P1-12 | Handlers | Go-live is refused unless the issue is `approved` (test); `/today` returns the new issue after go-live | Not Started |
| P5-05 | Critical | WF-05 approval form (exception-based: flagged items first) + `brief review approve/reject` CLI + `brief_record_review` guards + `edition_number` assignment at go-live + enforcement of the 30-edition full-review rule **per production epoch** | P5-04, P3-05 | `n8n/WF-05.json`, SQL | Approval with any unchecked checklist item is rejected; editions ≤30 cannot skip review | Not Started |
| P5-07 | Medium | Accessibility and mobile pass | P5-01 | — | Lighthouse accessibility ≥95 and performance ≥90 on the issue page (mobile) | Not Started |
| P5-08 | Medium | Cloudflare Web Analytics (cookieless) on the site | P1-12 | Snippet | Page views visible in the dashboard; no cookies set | Not Started |
| P5-09 | Critical | Phase 5 gate: controlled-launch readiness ([RISKS_AND_OPERATIONS §11](docs/RISKS_AND_OPERATIONS.md#11-compliance-checklist-before-phase-5-launch)); Supabase Pro decision | P5-01…P5-08 | `docs/gates/phase-5.md` | Checklist complete; restore rehearsal done | Not Started |

### E.Phase 6 — Instagram automation

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P6-01 | Critical | Verify Meta docs: publishing limits, polling, container expiry, caption-edit support, API version, insights metrics; update ADR-011 and RISKS §2 | — | Updated ADR | Each fact recorded with a source link and date | Not Started |
| P6-02 | Critical | Test container creation on a test account; test whether a presigned R2 URL is accepted as `video_url` (V-18) | P6-01, P6-02U | Runbook `docs/runbooks/meta-app.md` | Container creation succeeds; the presigned vs public fallback decision is recorded | Not Started |
| P6-03 | Critical | Token storage (pgcrypto), `brief token status`/`store`/`refresh`, `refresh_token` job, WF-07 | P6-02, P2-02 | `brief/publish/tokens.py`, `n8n/WF-07.json` | Token never appears in logs (scrubber test); refresh runs and updates expiry; alert at under 7 days | Not Started |
| P6-04 | Critical | `publish_reel` (`brief publish reel` / `check`): pre-flight, container, polling, `check_container`, `media_publish`, `publishing_jobs` state machine | P6-03, P5-04 | `brief/publish/instagram.py` | Contract tests with recorded responses for FINISHED, ERROR, EXPIRED, timeout; max 1 attempt; caption hash enforced | Not Started |
| P6-05 | Critical | `reconcile_reel` + manual-media-id path | P6-04 | `brief/publish/reconcile.py` | Simulated ambiguous publish resolves without a second post in all 4 reconcile branches (tests) | Not Started |
| P6-06 | High | WF-06 at 20:00 IST on `PUBLISH_DAYS` + "publish now" form + 22:00 late cutoff → `held` | P6-04, P3-05 | `n8n/WF-06.json` | Publish is refused unless the issue is `site_live` **and approved**; a late issue goes to `held` with an alert; no run on non-publishing days | Not Started |
| P6-07 | High | Dry-run mode (container only, no publish) + ≥5 test publications on a secondary test account | P6-04 | Test log | 5/5 test publishes reconciled, 0 duplicates | Not Started |
| P6-08 | Critical | Phase 6 gate review | P6-01…P6-07 | `docs/gates/phase-6.md` | 10 consecutive automated daily publishes, all reconciled to a media id or an explicit state, 0 duplicates | Not Started |

### E.Phase 7 — Analytics and audience ownership

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P7-01 | Critical | Select an email provider (ADR-010) with verified pricing, double opt-in, API, domain authentication and export | — | ADR-010 Accepted | Comparison table with dates checked; provider chosen | Not Started |
| P7-03 | High | Signup form on the site (provider-hosted or embed); SPF/DKIM/DMARC configured | P7-01, P7-02 | Form | A double opt-in test is received and confirmed; unsubscribe works | Not Started |
| P7-04 | High | `send_email` job (`brief email send`): campaign per issue from `edition_json`, idempotent via the provider campaign id; triggered after `published` or `site_live` | P7-03 | `brief/email/` | One send per issue even across retries (test with a mocked provider) | Not Started |
| P7-05 | High | Instagram insights: `collect_metrics` job (`brief metrics collect`) at 24 h, 72 h and 7 d + `reel_metrics` migration + WF-08 | P6-08 | Handler, migration | Metrics stored for 3 windows per Reel; the metric names match the current API (P6-01) | Not Started |
| P7-06 | Medium | Site metrics: Cloudflare Web Analytics export into `site_metrics`; decide on outbound-click measurement | P5-08 | Decision + importer | Weekly sessions per issue available in the report | Not Started |
| P7-07 | High | KPI section in WF-13 (business plan §10 KPIs with the correct denominators) | P7-05, P7-06 | `n8n/WF-13.json` v2 | Profile→issue CTR uses profile visits as its denominator (as the plan specifies) | Not Started |
| P7-08 | Medium | Feedback guardrails: category tie-break weights as versioned config; test that verification thresholds can't be changed by metrics code | P3-03 | Config + test | A change to the weights bumps `score_version` and writes a changelog entry | Not Started |
| P7-09 | Low | Cross-posting evaluation (YouTube Shorts, LinkedIn) — decision doc only | P6-08 | `docs/decisions/cross-posting.md` | Decision recorded; no build before 10 consecutive reconciled Instagram runs | Not Started |

### E.Phase 8 — Commercial validation

| ID | Priority | Task | Depends on | Output | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| P8-02 | Critical | Disclosure policy and templates (verify the latest ASCI/CCPA guidance); `sponsor_flag` + C11 enforcement; sponsored-segment card | P3-08 | Policy page + code | An issue with a sponsor flag and no disclosure cannot be approved (test) | Not Started |
| P8-04 | Medium | Affiliate links: `rel="sponsored nofollow"`, disclosure near the link | P8-02 | Template change | Template test checks the attributes and the disclosure | Not Started |
| P8-06 | High | Commercial pilot gate review | P8-01…P8-05 | `docs/gates/phase-8.md` | One disclosed pilot run or a documented repositioning decision | Not Started |

## F. Verification tracker

Statuses: **Verified (official)** means read on the provider's documentation, with the date. **Unverified** means not yet checked officially and not to be treated as confirmed. Details and current understanding are in [RISKS_AND_OPERATIONS §2](docs/RISKS_AND_OPERATIONS.md#2-facts-to-re-verify-before-relying-on-them).

| V-ID | Item | Status | Verify in | Owner |
|---|---|---|---|---|
| V-01 | Anthropic model names and base prices | **Verified (official)**, 2026-11-07 | Re-check at P3-01 | Eng |
| V-02 | Anthropic Batch discount (50%) | **Verified (official)**, 2026-11-07 | — | Eng |
| V-03 | Anthropic cache-hit prices | **Verified (official)**, 2026-11-07 | — | Eng |
| V-04 | Structured outputs on Haiku 5.5 / Sonnet 5.5 | **Verified (official)**, 2026-11-07 | Re-check at P1-09 | Eng |
| V-05 | Ollama JSON-schema `format` | **Verified (official)**, 2026-11-07 | — | Eng |
| V-06 | Ollama model unload / `keep_alive` | Unverified | P2-17 | Eng |
| V-07 | Local model fit and quality on a 16 GB M5 | Unverified (measure) | P1-09, P2-17 | Eng |
| V-08 | Paid TTS vendor prices and terms (optional fallback only) | Unverified | Only if the fallback is needed | Eng |
| V-09 | Kokoro code and weights licences | **Verified (official)**, 2026-11-08 (LICENSE file; model card) | Re-check at P1-05 | Eng |
| V-10 | Domain price | Unverified | P0-05 | User |
| V-11 | Cloudflare Pages and R2 free tiers | Unverified | P1-12 | Eng |
| V-12 | Supabase Free limits and backups; Pro price | Unverified | P2-01 | Eng |
| V-13 | Hetzner VPS price | Unverified | P2-12U | User |
| V-14 | healthchecks.io free plan | Unverified | P2-13U | User |
| V-15 | GitHub Free Actions allowance | Unverified | P0-04 | Eng |
| V-16 | Apify free credit and Starter price | Unverified | P2-10 | Eng |
| V-17 | n8n licence fit | Unverified | P2-12 | Eng |
| V-18 | Instagram API limits, polling, caption editing, presigned `video_url` | Unverified | P6-01, P6-02 | Eng |
| V-19 | Instagram long-lived token rules | Unverified | P6-03 | Eng |
| V-20 | Email provider tiers | Unverified | P7-01 | Eng |
| V-21 | ASCI / CCPA disclosure wording | Unverified | P8-02 | User |
| V-22 | India DPDP obligations | Unverified | P7-02 | User |
| V-23 | espeak-ng licence (Kokoro, Piper dependency) | Unverified | P1-05 | Eng |
| V-24 | Piper `en_GB-cori-medium` commercial use (public-domain dataset vs Piper's "personal use and research" statement) | Unverified; needs review | P1-05 | Eng + user |
