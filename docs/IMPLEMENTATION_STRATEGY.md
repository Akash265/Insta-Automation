# Implementation Strategy — AI Daily Brief

Status: **Planning baseline v1** (2026-11-07). Prepared from `AI_Daily_Brief_Business_Plan_Revised.pdf` (15 Oct 2026), `CLAUDE.md`, the founder's decisions of 2026-11-07, and searches of current provider documentation and pricing.

## Document map

| Doc | Read it for |
|---|---|
| **IMPLEMENTATION_STRATEGY** (this) | Scope, discovery, cost model, execution order |
| [SYSTEM_ARCHITECTURE](SYSTEM_ARCHITECTURE.md) | Components, data flow, state machines, topology, env vars |
| [DATABASE_DESIGN](DATABASE_DESIGN.md) | Tables, constraints, duplicate prevention, retention, edition JSON |
| [EDITORIAL_PIPELINE](EDITORIAL_PIPELINE.md) | Sources, freshness, rubric, hard rules, claims, review, corrections |
| [WORKFLOWS](WORKFLOWS.md) | Job types, `brief` CLI, n8n workflows, daily timeline, Phase 1 runbook |
| [IMPLEMENTATION_ROADMAP](IMPLEMENTATION_ROADMAP.md) | Phases, gates, effort |
| [TECHNICAL_DECISIONS](TECHNICAL_DECISIONS.md) | ADRs and the conflict register |
| [RISKS_AND_OPERATIONS](RISKS_AND_OPERATIONS.md) | Risks, security, recovery runbooks, monitoring, privacy |
| [VALIDATION_EXPERIMENT](VALIDATION_EXPERIMENT.md) | The pre-registered 14-day Phase 1 experiment: workflow, thresholds, continue / pivot / stop |
| [DECISION_REVIEW](DECISION_REVIEW.md) | Pre-implementation decision review (2026-11-07): automation, hybrid LLM, open decisions, 90-day model |
| [../TASKS.md](../TASKS.md) | Backlog: IDs, dependencies, acceptance criteria, status |

## 1. Summary

**What we are building.** A daily AI-news product. One reviewed edition record produces a 60–90 s faceless Instagram Reel, a source-linked web issue (`/today`), a searchable archive and, later, an email. The core is an **editorial engine**: source tiers, freshness rules, a transparent 100-point rubric, hard rejection rules, and claim-to-evidence verification. Automation produces the outputs; it does not decide what is true.

**How.** A single tested Python package, `brief`, runs everything. Postgres (Supabase) is the system of record and the job queue. A Mac worker does the heavy media work. A thin n8n layer on a small VPS provides schedules, editor forms and alerts. The site is static on Cloudflare Pages, with media on R2. LLM calls use **approved hybrid routing**: local Ollama for tagging and duplicates (kept only if it passes measured benchmarks), Haiku 5.5 for ranking suggestions, Sonnet 5.5 for claims, script and second-pass verification, and Opus for evaluation only, under a $35/month cap. TTS is a paid API with a hash cache. Instagram publishing goes only through Meta's official API, with idempotency and reconciliation.

**What we are building first.** Phase 1 is a manual 14-day prototype supported by a small toolkit: `brief validate`, `brief render`, `brief site build`/`deploy`, plus an optional LLM draft. It has no database and no n8n. Its purpose is to prove the editorial value and the time cost before anything is automated. It runs as a pre-registered [14-day validation experiment](VALIDATION_EXPERIMENT.md), with a reader panel, an accuracy audit and explicit continue / pivot / stop rules. If it passes, an **approved public soft launch at 5 editions a week** follows from about Day 15, while automation is built ([ADR-017](TECHNICAL_DECISIONS.md#adr-017)). Human approval stays mandatory for every edition.

**What we are deliberately postponing.**
- Broad scraping (Apify only for named feedless tier-1 sources, after Phase 2).
- pgvector and embeddings.
- Automated Instagram publishing (Phase 6).
- Email (Phase 7).
- Cross-posting (after 10 consecutive reconciled runs).
- Monetisation (Phase 8).
- Generative video and avatars.
- Multi-language editions.
- User accounts, a custom dashboard, a mobile app.
- Comment and DM automation (never).

## 2. Technical discovery report

| Area | Finding |
|---|---|
| Project structure | Only `AI_Daily_Brief_Business_Plan_Revised.pdf` and `CLAUDE.md`. No source code, no `docs/` before this package, **not a git repository** |
| Existing implementation | **None.** No working components, configuration, dependencies or tests |
| Local environment (verified 2026-11-07) | Apple M5, 16 GB RAM, macOS. Present: Docker, git, Node 24.15, system Python **3.9.6** (too old; the plan uses Python 3.12 via `uv`). Missing: ffmpeg, ollama, psql, n8n, gh |
| Dependency inventory | None yet. The target inventory with a justification per dependency is in [SYSTEM_ARCHITECTURE §10](SYSTEM_ARCHITECTURE.md#10-technology-inventory-target) |
| Missing capabilities | Everything: ingestion, editorial engine, media, site, publishing, email, analytics, ops |
| Configuration / env | Defined in [SYSTEM_ARCHITECTURE §9](SYSTEM_ARCHITECTURE.md#9-configuration--environment-variables). Phase 1 needs only the LLM key (optional), TTS key, Cloudflare token/account and R2 keys |
| Security / deployment concerns | No secrets exist yet, which is the right moment to set the policy (P0-01: gitleaks, `.env` ignored). Key future concerns: the Instagram token lifecycle, n8n exposure, Supabase free-tier backup gaps, R2's lack of a hard spend cap, and prompt injection from scraped text |
| Technical debt | None in code. Planning debt was found in the business plan and the original CLAUDE.md (below) |
| Discrepancies | 9 conflicts between the business plan, the original CLAUDE.md and the founder's choices. Each is resolved in the [conflict register](TECHNICAL_DECISIONS.md#conflict-register-where-this-plan-departs-from-the-business-plan-or-the-original-claudemd). The most consequential: n8n-centric logic → Python core; local LLM/TTS → APIs; page published before the QA gate → preview-then-approve; mixed state list → separate state machines |

## 3. Product scope

| Component | MVP (by the Phase 6 gate) | Later |
|---|---|---|
| Reel | 60–90 s, 3–7 stories, cards + narration + burned subtitles, date, source attribution, CTA; 20:00 IST via API | A/B hooks, YouTube Shorts |
| Web issue | `/today`, `/issues/YYYY-MM-DD/`, summary + why it matters + publisher + dates + "Read original" + limitations + correction notes; JSON-LD | Full-text search (Pagefind) |
| Archive | Date list; topic, company and source pages (≥3 stories); client-side filters | Weekly "what changed" pages (premium candidate) |
| Email | — (Phase 7: provider-hosted double opt-in, one campaign per issue) | Segmented digests |
| Editorial engine | Tiers, rules R01–R12, rubric v1.0, claims and evidence, checks C01–C12, human approval of every edition; full review of the first 30 manual and first 30 automated editions, the next 10 after any material error, and high-risk editions | pgvector clustering, learned ranking (within the guardrails) |
| Ops | Queue, outbox, watchdog alerts, backups, cost caps, audit | Status page |

## 4. Target architecture (summary)

See [SYSTEM_ARCHITECTURE](SYSTEM_ARCHITECTURE.md) for diagrams. The key choices, with their ADRs:

| Layer | Choice | Why | ADR |
|---|---|---|---|
| Logic | Python 3.12 package `brief` (Typer CLI + job handlers) | Testable, deterministic, portable | 001 |
| Orchestration | n8n CE on a small VPS: cron, forms, alerts only | Founder-friendly forms and alerts without logic lock-in | 001 |
| Control plane | Supabase Postgres + `jobs` queue + `outbox_events` | Managed DB; no extra queue infrastructure | 002, 007 |
| Heavy compute | Mac worker (launchd), cutoff 17:00 IST | ₹0 and enough CPU; outbound-only | 005 |
| Collection | RSS/Atom, GitHub and arXiv APIs; Apify only for allow-listed feedless sources | Cheapest and most auditable; MCP for research only | 014 |
| LLM | **Hybrid routing:** local Ollama (~8B) for tagging and same-event checks; Haiku 5.5 for triage; Sonnet 5.5 for claims, script and critic (Opus only if it earns it); structured output; $35/month cap with a degradation ladder | Pay only where quality matters; resilience for routine tasks | 003 |
| TTS | API vendor from the bake-off, per-segment hash cache, Kokoro fallback | Quality; negligible cost | 004 |
| Video | Pillow cards + FFmpeg, ASS subtitles | Cheap and deterministic | 015 |
| Site | Python/Jinja static build → Cloudflare Pages (wrangler direct upload) | One language, free hosting | 006 |
| Storage | R2: private bucket (MP4s via presigned URL, snapshots, backups) and public bucket (covers after approval) | Nothing public before approval | RISKS §3.4 |
| Publishing | Instagram API with Instagram Login; container → poll → publish; reconcile | Official, idempotent | 011 |
| Email | Hosted provider as the system of record (Phase 7) | Keeps PII out of our DB | 010 |

## 5. Phases and gates

| Phase | Gate (summary) | Effort |
|---|---|---|
| 0 Repo + discovery | Scaffold ready (brand and domain are needed only by gate G4) | 2–3 d |
| 1 Manual prototype | [Pre-registered experiment](VALIDATION_EXPERIMENT.md#3-hypotheses-metrics-and-thresholds-pre-registered): ≥ 10 editions; 100% evidence; 0 unresolved material errors; panel ≥ 3.8/5; stable renders and deploys (+ should-pass H1, H3, H5) | 8–10 d + 14 d run |
| 2 Ingestion | 10 days with no silent failures; dedupe recall ≥90%; restore test | 8–10 d + 10 d |
| 3 Editorial intelligence | 10 consecutive editions with a prepared issue by 18:00; 0 unsupported claims reaching review; cost within cap | 10–12 d + 10 editions |
| 4 Media | 10 consecutive automated renders with no manual fix | 3–4 d |
| 5 Website + archive | Compliance checklist; DB-backed site replaces the toolkit site (the public soft launch has already started at G4) | 5–6 d |
| 6 Instagram API | 10 consecutive reconciled scheduled publishes, 0 duplicates | 5–7 d + Meta lead time |
| 7 Email + analytics | 30+ editions with KPIs; 90-day continue/pivot/pause decision | 5–6 d |
| 8 Commercial | One disclosed pilot or a repositioning decision | 2–3 d + sales |

Detail is in [IMPLEMENTATION_ROADMAP](IMPLEMENTATION_ROADMAP.md), including the [approved 90-day plan](IMPLEMENTATION_ROADMAP.md#approved-90-day-plan). Phases 0–1 fall in the preparation window. By Day 90 the target is Phases 2–4 plus the deploy jobs. Phases 5–8 follow Day 90, and gates, not dates, decide progress.

## 6. Cost model

**Signed off on 2026-11-07**, with PD-01 to PD-07 approved. It applies the approved decisions:
- a ₹15,000 cash ceiling that **includes preparation-window spend** (PD-01);
- 5 editions a week from a passed experiment;
- hybrid LLM routing with graduated caps: **$10** for Days 1–30, **$20 interim** for Days 31–60 (PD-02), and **$35** for Days 61–90;
- a voice cap of **$10/month**, retained until measured usage justifies reconsidering it (PD-07);
- founder time at ₹500/h.

It supersedes the decision-review draft (₹5,190 / ₹12,480 / 349 h) and the finalisation draft (₹14,680 worst case / 428 h). §6.5 and §6.11 reconcile them.

**Conventions:**
- **₹88 = $1** (business plan convention).
- **Expected** is the planning estimate. **Max** is the hard cap enforced in code or by the vendor's spend limit, or the top of a quoted range.
- Token and character volumes are **assumptions until measured** (ADR-003, P1-09).
- Prices exclude taxes; GST on imported services may apply and is not modelled.
- Items marked *(verify)* are not yet checked against an official source (§6.10).

**Budget periods follow the plan windows, not calendar months.** `config/budget_periods.yaml` (P1-36) defines Preparation, Days 1–30, Days 31–60 and Days 61–90, each with its LLM and voice cap. That way the caps enforced in code line up one-to-one with the rows below, and nothing is counted twice.

### 6.1 Timeline the model assumes ([ROADMAP](IMPLEMENTATION_ROADMAP.md#approved-90-day-plan))
| Window | Work | Public editions |
|---|---|---:|
| Preparation, Day −18 to 0 | Phase 0 and the Phase 1 toolkit; bake-offs; panel and auditor recruitment; [G1 readiness gate](gates/G1_DAY1_READINESS.md) | 0 |
| Days 1–14 | Validation experiment (private) | 0 (14 private) |
| Days 15–30 | Soft launch, 5 a week (if the experiment passes); Phase 2 engineering starts | ≈ 11 |
| Days 31–60 | Automation development (Phases 2–3) | ≈ 22 |
| Days 61–90 | Phase 4 and deploy automation; automated workflow after its gates; 90-day review | ≈ 22 |

**PD-01 (approved):** all preparation-window spend counts **inside** the ₹15,000 ceiling. That is about ₹900 expected for the two bake-offs (₹1,300 max), plus the domain if it is bought before Day 1.

### 6.2 One-time setup (cash)
| Item | When | Expected | Max | How the max is enforced |
|---|---|---:|---:|---|
| Domain, year 1 | Before G4 (Day 15); may be bought earlier | ₹1,500 | ₹2,500 | Business plan range *(verify registrar)* |
| Voice (TTS) bake-off, about 100k characters across vendors | Preparation | ₹450 | ₹700 | Preparation voice cap of $8, plus vendor spend limits (P1-27) |
| LLM bake-off: 10 stories × Haiku, Sonnet, Opus (evaluation) × about 3 runs; local models free | Preparation | ₹450 | ₹600 | Preparation LLM cap of $7, plus the Anthropic Console spend limit (P1-26) |
| Brand assets (OFL fonts, built by the founder); Meta developer setup | — | ₹0 | ₹0 | — |
| **Subtotal** | | **₹2,400** | **₹3,800** | |

### 6.3 Recurring infrastructure (cash)
| Item | Days 1–30 | Days 31–60 | Days 61–90 | Expected | Max | Basis |
|---|---:|---:|---:|---:|---:|---|
| VPS for n8n (from Day 31) | — | ₹450 | ₹450 | ₹900 | ₹1,200 | About €3.5–4.5/month *(verify P2-12U)* |
| Supabase | — | ₹0 | ₹0 | ₹0 | ₹0 | Free plan through Day 90 (OD-04, proposed) *(verify P2-01)* |
| Cloudflare Pages + R2, healthchecks.io, private GitHub repo, Telegram | ₹0 | ₹0 | ₹0 | ₹0 | ₹0 | Free plans *(verify; R2 has no hard spend cap, so usage is checked weekly)* |
| **Subtotal** | | | | **₹900** | **₹1,200** | |

### 6.4 API usage (cash, Days 1–90; bake-offs are only in §6.2)

**LLM API:**

| Window | Use | Cap (approved) | Expected | Max |
|---|---|---|---:|---:|
| Days 1–30 | Optional script drafting for about 25 editions | **$10** | ₹200 | ₹880 |
| Days 31–60 | Drafting about 22 editions; local-fallback tests; Phase 3 development and replay testing (**assumed** about $5) | **$20 interim (PD-02)** | ₹640 | ₹1,760 |
| Days 61–90 | About 15 automated editions on the hybrid pipeline + about 7 drafted; regression set; one Opus evaluation run | **$35** | ₹1,150 | ₹3,080 |
| **LLM subtotal** | | | **₹1,990** | **₹5,720** |

**Voice generation (TTS), a separate line from the LLM:**

| Window | Use | Cap | Expected | Max |
|---|---|---|---:|---:|
| Days 1–30 | About 25 editions × about 1.7k characters | **$10 (PD-07)** | ₹100 | ₹880 |
| Days 31–60 | About 22 editions + development re-renders (mostly cache hits) | $10 | ₹150 | ₹880 |
| Days 61–90 | About 22 editions | $10 | ₹150 | ₹880 |
| **TTS subtotal** | Lower-cost vendors; a premium voice would be about ₹300–700/month and still within the cap | | **₹400** | **₹2,640** |

**PD-07 (approved):** the $10 voice cap stays until the vendor comparison is done. A $5 cap is reconsidered only after measured usage (P1-39). That change would lower the max by ₹440 per remaining window.

Apify is ₹0: the free-plan credit blocks rather than bills, and the MVP may use no Actors. Email is ₹0 because it starts in Phase 7, after Day 90.

### 6.5 Founder time (not cash)
| Window | Engineering | Editorial | Review, ops, setup | Total |
|---|---:|---:|---:|---:|
| Preparation (Day −18 to 0) | 75 h (Phase 0 + toolkit, about 12 days; budget tracker P1-36) | — | 14 h (brand, sources, panel, auditor, accounts, rubric sign-off, G1 check) | **89 h** |
| Days 1–14 (experiment) | 6 h (toolkit fixes) | 35 h (14 × 150 min) | 10.5 h (audit intake, notes, Day 7 checkpoint, gate) | **51.5 h** |
| Days 15–30 (soft launch) | 30 h (Phase 2 start) | 24 h (≈ 11 × 130 min) | 6 h (policy pages, weekly review) | **60 h** |
| Days 31–60 (automation) | 90 h (Phase 2 finish, Phase 3) | 44 h (≈ 22 × 120 min) | 4.5 h (including the voice-cap review) | **138.5 h** (≈ 32 h/week; R24) |
| Days 61–90 (reliability) | 54 h (Phase 3 finish, Phase 4, deploy jobs) | 33 h (≈ 22 × ~90 min) | 7 h (weekly reviews, 90-day review) | **94 h** |
| **Total** | **255 h** | **136 h** | **42 h** | **≈ 433 h** |

- **At ₹500/h (approved):** ≈ **₹2,16,500** imputed in total: ≈ ₹44,500 for preparation (89 h) and ≈ ₹1,72,000 for Days 1–90 (≈ 344 h).
- **Three different workloads:**
  1. **Initial manual validation:** about 150 min per edition, about 35 h over 14 days.
  2. **Engineering and automation:** about 255 h through Day 90. This is a one-off build cost.
  3. **Mature editorial:** a target of about 20 h/month by months 5–6, not yet measured ([EDITORIAL_PIPELINE §13](EDITORIAL_PIPELINE.md#13-human-involvement-model)).
- **Reconciliation:**
  - 349 h (proposal) → 428 h (finalisation): +54 engineering, because Phase 4 and the deploy jobs now fall before Day 90; +13 editorial, because the soft launch starts at Day 15; +12 review and ops, for the panel, auditor, policy pages and 90-day review.
  - 428 h → **433 h** (sign-off): **+5 h**. That covers the budget-period and ceiling tracker (3 h engineering), the rubric v1.1 sign-off and G1 readiness check (2 h), and the voice-cap review (0.5 h).
- **Not modelled:** local-model maintenance (≤ 1 h/month, assumed inside review and ops) and electricity.

### 6.6 Optional expenses (only from headroom; approved in the weekly review)
| Item | Amount | Status / condition |
|---|---:|---|
| Template designer (fixed scope) | ₹0–5,000 | Only if the panel flags visuals, **and** spending rule 1 allows it |
| Reader panel incentives | ₹0–2,000 | **Not approved.** The panel is unpaid |
| Paid auditor | ₹0–3,000 | Not needed: a volunteer auditor is confirmed |
| Supabase Pro before Day 90 | ₹2,200/month *(verify)* | Only if the Free-plan backup and restore tests fail, **and** rule 1 allows it |
| Opus in production | ≈ +₹620/month | **Not approved.** Needs measured evidence and a founder decision (ADR-003) |
| Paid promotion | ₹0 | Not before organic evidence (business plan policy) |

### 6.7 90-day totals vs the ₹15,000 ceiling
| Cash category | Expected | Worst case (every approved cap hit) |
|---|---:|---:|
| One-time setup (includes pre-Day-1 bake-offs) | ₹2,400 | ₹3,800 |
| Recurring infrastructure | ₹900 | ₹1,200 |
| LLM API ($10 / $20 / $35) | ₹1,990 | ₹5,720 |
| Voice generation ($10 per window) | ₹400 | ₹2,640 |
| **Total cash** | **₹5,690** | **₹13,360** |
| **Headroom under ₹15,000** | ₹9,310 | **₹1,640** |

By window (expected): preparation ₹900 · Days 1–30 ₹1,800 (including the domain) · Days 31–60 ₹1,240 · Days 61–90 ₹1,750.

**The worst case is within the ceiling, so no forecast reduction is needed.** One interpretation check: the sign-off instruction "retain the existing $35 cap for other approved periods" is read as **$35 for Days 61–90 only**, with the existing approved **$10 for Days 1–30**. If Days 1–30 were also given $35, the worst case would be **₹15,560**, exceeding the ceiling by ₹560. The specific reduction needed is to keep Days 1–30 at ≤ $28 (or keep the approved $10). The plan uses $10.

**Spending safeguards (retained):**
1. An optional item is approved only if the **projected max**, meaning actual spend to date plus every remaining cap, stays at or below ₹15,000. Before any actuals exist, headroom is ₹1,640, so the ₹5,000 designer cannot be approved yet. Rule 1 is re-applied at the **Day 45 review** (P1-35).
2. If actual spend passes **₹10,000 before Day 60, all optional spend is frozen.**
3. Caps are enforced in code per budget period (LLM and voice), plus vendor spend limits on every paid account, plus Apify per-run caps. `brief cost report` shows actual spend by category and the projected max against ₹15,000 (P1-36).

### 6.8 Fully loaded cost: the honest total
| | Expected | Worst case |
|---|---:|---:|
| Cash | ₹5,690 | ₹13,360 |
| Founder time (433 h × ₹500) | ₹2,16,500 | ₹2,16,500 |
| **Fully loaded, preparation + 90 days** | **≈ ₹2.22 lakh** | **≈ ₹2.30 lakh** |

Cash is about 3–6% of the real cost. Every monthly report (WF-13) shows **cash contribution** and **fully loaded contribution**.

### 6.9 Monthly run-rate after Day 90 (planning only; outside the ceiling)
| Item | Soft launch, automated pipeline, Supabase Free | After moving to Supabase Pro |
|---|---:|---:|
| VPS | ₹450–600 | ₹450–600 |
| Supabase | ₹0 | ₹2,200 *(verify)* |
| LLM (22 editions + regression and evaluation; $35 cap) | ≈ ₹1,250 | ≈ ₹1,250 |
| TTS | ₹100–150 (premium voice ≈ ₹300–700) | same |
| Domain, amortised | ₹125 | ₹125 |
| **Total** | **≈ ₹1,900–2,150** | **≈ ₹4,100–4,350** |

Email (Phase 7, ADR-010) and Apify Starter (only if justified) would be extra. Returning to 7 editions a week, decided only at the Day-90 review (PD-04), would add about ₹350/month in LLM costs and about 15–17 h/month of editorial time.

### 6.10 Prices and limits still needing official verification
Only these were checked on official pages (2026-11-07):
- Anthropic model prices, the Batch discount and cache prices;
- structured-output support;
- Ollama's JSON-schema `format`.

Everything else is **unverified** until its task records a source and date ([TASKS.md verification tracker](../TASKS.md#f-verification-tracker), V-06 to V-22).

### 6.11 Sign-off reconciliation checks (2026-11-07)
| Check | Result |
|---|---|
| Pre-Day-1 spend included (PD-01) | **Yes.** The bake-offs (₹900 expected, ₹1,300 max) are in §6.2, and the domain is counted once whatever its purchase date |
| Interim LLM cap applied only to Days 31–60 (PD-02) | **Yes.** $10 / $20 / $35 by budget period; the preparation bake-off has its own $7 cap inside §6.2 |
| API and voice not double-counted | **Yes.** Bake-off spend appears only in §6.2; §6.4 covers pipeline usage in Days 1–90 only; LLM and voice are separate lines; budget periods match the rows one-to-one |
| ₹15,000 ceiling enforced | **Yes.** Worst case ₹13,360, headroom ₹1,640; projected-max rule; code caps and vendor spend limits |
| Optional spend freeze retained | **Yes.** Frozen if actual spend passes ₹10,000 before Day 60 |
| Founder labour reported separately at ₹500/h | **Yes.** ≈ 433 h, ≈ ₹2,16,500, never mixed into cash |
| Forecast not reduced to fit | **Yes.** Expected unchanged at ₹5,690; the worst case fell from ₹14,680 to ₹13,360 only because of the approved PD-02 cap |

## 7. Top risks

From [RISKS_AND_OPERATIONS §1](RISKS_AND_OPERATIONS.md#1-risk-register):
1. **A false or exaggerated claim published.** Mitigated by evidence mapping, checks and human review.
2. **Founder time stays above 2.5 h per edition.** Measure from day 1; automate only the measured bottlenecks.
3. **Instagram API, token or policy failures.** Use the official flow, reconciliation, a manual fallback and token alerts.
4. **"Generic AI summary" perception.** Original why-it-matters, restraint and visible sourcing.
5. **Mac availability at cutoff.** Heartbeat alerts plus a location-agnostic worker.

## 8. Execution order and first milestone

**Milestone M1, readiness gate G1 (Day 0)**, using the [G1 checklist](gates/G1_DAY1_READINESS.md): the toolkit works (`validate → render → site deploy` on fixture and then real data), the panel and the auditor are confirmed, and the thresholds are signed off. Only then does experiment Day 1 start.

**User actions before Day 1.** The full list, with IDs, is in [TASKS.md, user actions](../TASKS.md#a-user-actions):
- approve the source list and the reference roundups;
- recruit the panel and create the form;
- recruit and brief the auditor;
- create the accounts that must be in your name (Cloudflare; the Anthropic Console with a spend limit, optional for the experiment; TTS bake-off vendors);
- sign off the thresholds;
- pass the [G1 readiness checklist](gates/G1_DAY1_READINESS.md);
- block about 3 h each evening for 14 days.

**First 10 engineering tasks, in order:**
1. **P0-01**: git init, `.gitignore`, `.env.example`, gitleaks
2. **P0-02**: `uv` Python 3.12 scaffold, `brief` CLI, ruff/mypy/pytest
3. **P0-03**: ffmpeg + wrangler pinned, `brief doctor`
4. **P1-02**: edition pydantic models (including every [audit-trail field](EDITORIAL_PIPELINE.md#14-mandatory-editorial-audit-trail)) + JSON Schema + fixtures
5. **P1-03**: `brief validate` (blocking and warning checks; C01 enforces the audit trail)
6. **P1-04**: safe fetcher + `brief linkcheck`
7. **P1-05**: TTS bake-off → vendor decision
8. **P1-07**: card templates (Pillow) with golden tests
9. **P1-06** + **P1-08**: TTS synth with cache, then subtitles
10. **P1-10**: `brief render` with ffprobe validation

Then come P1-11 and P1-12 (site), P1-19 (experiment instruments) and P1-14 (reports). P1-09 and P1-13 (LLM) are optional.

**How completion is measured.** Every task has acceptance criteria in TASKS.md, and a task is `Done` only when they are verified. Each phase closes with a gate document of measured evidence. The Phase 1 gate applies the pre-registered rules in [VALIDATION_EXPERIMENT §8](VALIDATION_EXPERIMENT.md#8-decision-rules-at-day-14-p1-17).

## 9. Open decisions

The founder's decisions of 2026-11-07 are recorded as **approved** in [DECISION_REVIEW §0](DECISION_REVIEW.md#0-finalised-decisions-2026-11-07). PD-01 to PD-07 were **approved at sign-off** on 2026-11-07. The remaining items are the open decisions not needed before Day 90 (OD-04, OD-05, OD-07, OD-09, OD-10, OD-11). They are tracked in [TASKS.md, decisions](../TASKS.md#b-decisions).

The one decision automation cannot settle is still this: **is the format distinctive and useful enough to earn repeat attention?** The [validation experiment](VALIDATION_EXPERIMENT.md) (H4, H5) and the 90-day review answer it.
