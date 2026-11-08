# Technical Decisions (ADRs) — AI Daily Brief

Status values: **Accepted**, **Accepted (provisional, revisit at gate)**, **Open (default chosen)**, **Superseded**.
Prices and limits below come from searches on **2026-11-07**. Sources often disagreed, and those figures are marked *(verify)*. Re-check each one against the official page before spending money or committing ([RISKS_AND_OPERATIONS §2](RISKS_AND_OPERATIONS.md)).

## Conflict register: where this plan departs from the business plan or the original CLAUDE.md

| # | Business plan / original CLAUDE.md | This plan | ADR |
|---|---|---|---|
| 1 | n8n is the centre of the pipeline (Code nodes do normalisation, etc.) | Python package `brief` does all logic; n8n only schedules, shows forms and sends alerts | 001 |
| 2 | Local LLM via Ollama is the default; API is an optional fallback | **Approved hybrid:** local Ollama for tagging and duplicates (kept only if it passes measured benchmarks), Haiku for ranking suggestions, Sonnet for claims, script and second-pass verification; Opus for evaluation only; $35/month cap | 003 |
| 3 | Kokoro TTS is the default | API TTS is primary (cached by hash); Kokoro is the local fallback and a bake-off entrant | 004 |
| 4 | Issue page goes public at 19:00, quality gate at 19:15 | **Preview** deploy → review → production deploy → Reel. Nothing public before approval | 012 |
| 5 | One state list mixes story states with edition states | Separate machines for story, issue, publishing job and job | 012 |
| 6 | Final collection at 17:30 | Cutoff at 17:00 to give the Mac render a buffer | 005 |
| 7 | Entities `stories`, `story_claims`, `editions`, `edition_stories`, `metrics` | `candidate_stories`, `claims` + `evidence_records`, `daily_issues`, `issue_stories`, `reel_metrics`/`site_metrics` (a superset; mapping in DATABASE_DESIGN) | 009 |
| 8 | The planning prompt asks for a `newsletter_subscribers` table | The email provider is the system of record; no subscriber PII in our DB unless email is self-hosted | 010 |
| 9 | Plan budget of ₹1,000–3,500/month (lean MVP) | Soft-launch run-rate ≈ ₹1,900–2,150/month expected (Supabase Free). The signed-off 90-day cash model (including pre-Day-1 spend) is ≈ ₹5,690 expected and ≤ ₹13,360 with every approved cap hit, within the ₹15,000 ceiling. Founder labour ≈ 433 h (≈ ₹2.17 lakh at ₹500/h) is reported separately | 003, Strategy §6 |
| 10 | "Daily" publication from launch | **Approved:** public soft launch at **5 editions a week**, starting after a passed experiment (target Day 15), manual upload. A return to 7 a week is decided only at the Day-90 review (PD-04, approved) | 017 |
| 11 | First-30-editions review | **Approved:** full review for the first 30 manual **and** the first 30 automated editions; any material error → the next 10 editions in full review; human approval is mandatory for every edition | EDITORIAL_PIPELINE §9 |
| 12 | *Finalisation:* the request places the experiment at Days 1–14 | The experiment needs the Phase 0–1 toolkit (≈ 12 engineering days) first, so there is a **preparation window (Day −18 to Day 0)**. The 90 days count from experiment Day 1 | Roadmap |
| 13 | *Finalisation:* Days 31–60 automate ingestion through deployment | That is ≈ 29 engineering days plus stability windows, which doesn't fit in 30 days. Phase 2 engineering starts in Days 15–30; narration, render and deploy automation is expected in Days 61–75. **Dates are targets; gates decide** | Roadmap |
| 14 | *Finalisation:* the first 30 automated editions fall within Days 61–90 | At 5 a week, 30 editions take 6 weeks. Expect about 11–18 automated editions by Day 90, with the full-review period continuing past Day 90. The 90-day review uses partial automated-epoch data | Roadmap, EDITORIAL_PIPELINE §9 |
| 15 | *Finalisation:* a $35 cap during Phase 3 development (Days 31–60) | **Resolved at sign-off (PD-02 approved):** an interim $20 cap for Days 31–60 only; $10 for Days 1–30; $35 for Days 61–90. Worst case ₹13,360 (₹1,640 headroom). Giving Days 1–30 $35 as well would reach ₹15,560, over the ceiling | ADR-003, Strategy §6 |
| 16 | *Finalisation:* gates written as "10 consecutive days" vs a 5-a-week cadence | Editorial gates are measured in **consecutive editions** (publishing days); ingestion gates stay in calendar days. This is stricter in calendar time, never looser | Roadmap |
| 17 | *Finalisation:* panel questions moved from Yes/No to 1–5 | The Yes/No thresholds are mapped to "share rating ≥ 4" with the same percentages; nothing is loosened | VALIDATION_EXPERIMENT §3 |
| 18 | *Finalisation:* the ₹15,000 ceiling covers "the first 90 days", but preparation spend happens before Day 1 | **Resolved at sign-off (PD-01 approved):** all pre-Day-1 spend (about ₹900 expected, ₹1,300 max, plus the domain if bought early) counts inside the ₹15,000 | Strategy §6 |
| 19 | *Sign-off:* rubric v1.0 freshness measured wall-clock age, so important weekend stories in Monday's edition scored low | **PD-06 approved:** rubric v1.1 measures freshness against the **edition window** (Fri 17:00 → Mon 17:00 for Monday) using `event_at`; event and publication dates are shown separately; R03 still rejects old events. Daily-cadence scores are unchanged, so the experiment is unaffected | EDITORIAL_PIPELINE §5.2 |
| 20 | *Sign-off:* monthly caps vs plan windows | Caps are defined per plan window (`config/budget_periods.yaml`), not calendar month, so bake-off spend and pipeline spend can't be counted twice or slip into the wrong cap | ADR-003 |
| 21 | *Sign-off:* manual full-review counting | **PD-03 approved:** only public editions count toward the first 30 manual editions; private prototypes and experiment drafts don't count (they still get full review) | EDITORIAL_PIPELINE §9.2 |

---

<a id="adr-001"></a>
## ADR-001 — Python core, thin n8n
**Status:** Accepted (confirmed by the founder, 2026-11-07).
**Context:** Editorial rules, verification and idempotent publishing must be testable, reviewable in git and deterministic. n8n Code nodes are hard to unit-test, diff and version.
**Decision:** All domain logic lives in the `brief` Python package, exposed as a CLI and as job handlers. n8n (self-hosted Community Edition) only runs cron triggers, editor forms, notifications and alerts. It talks to Postgres through `brief_*` SQL functions and `v_*` views under a least-privilege role. Workflow JSON is exported to `n8n/`.
**Alternatives:**
- n8n-first: rejected, because logic would be untestable and spread across nodes.
- Python with cron only: viable, but loses the forms and alert routing the editor needs.
**Consequences:** n8n can be replaced (cron plus a small form app) without touching any logic. Licensing: n8n's Sustainable Use License allows internal use, and we don't expose workflow building to customers *(re-check before any B2B offering)*.

<a id="adr-002"></a>
## ADR-002 — Control plane: Supabase Postgres + small VPS for n8n
**Status:** Accepted (provisional; revisit at the Phase 3 gate).
**Context:** The founder chose a managed control plane. Facts *(verify)*:
- Free-plan projects pause after **7 days of inactivity**; our daily writes prevent that.
- Free plan: **500 MB database**, 2 projects.
- Daily backups are **not reliably included on Free**. Pro is **$25/month** per organisation and adds daily backups with 7-day retention.
**Decision:**
- Supabase Free for Phases 2–5, with our own nightly `pg_dump` to private R2 and a weekly restore test.
- Move to Pro (about ₹2,200/month, unverified, V-12) at the Phase 5 gate (OD-04, proposed), after Day 90, when losing data would hurt the audience.
- n8n runs on a separate small VPS (2 GB, Docker Compose + Caddy) so it can alert when the Mac is down.
**Alternatives:**
- Postgres on the VPS: cheaper at scale, but adds database operations work for the founder.
- Everything on the Mac: no independent alerting.
**VPS sizing and cost (decision review):** the Hetzner entry ARM/x86 plans (CAX11, CX22/CX23) are listed by secondary sources at about **€3.5–4.5/month** after Hetzner's April and June 2026 price changes. The sources disagree, so verify on hetzner.com before buying (P2-12). The plan budgets **₹450–600/month** including tax and FX headroom. An **external dead-man's switch** (healthchecks.io free Hobbyist plan, 20 checks, Telegram integration, per its docs and secondary sources) pings from the worker, the n8n host and the backup job, so a dead VPS or Mac is detected by something outside our own infrastructure.
**Cheaper alternative, not recommended:** run n8n on the Mac until the Phase 5 gate, saving about ₹1,000 over 90 days. Rejected because the founder's topology places the scheduler in the control plane, and the Mac sleeping would silence the schedules.
**Data volume check:** about 200 candidates/day × ~3 KB ≈ 0.6 MB/day. With the 180-day prune that stays well under 500 MB. Snapshots go to R2, not the database.

<a id="adr-003"></a>
## ADR-003 — LLM: hybrid routing (local Ollama + hosted Haiku + Sonnet; Opus for evaluation only)
**Status:** **Approved 2026-11-07** (founder). Model choices per task are confirmed by measurement in P1-09 (bake-off) and P2-17 (local-tier benchmark). The caps per period, including the PD-02 interim $20 for Days 31–60, were approved at sign-off.
**Context:** Claim extraction and script quality decide whether we publish errors. Tagging and same-event checks are high-volume, low-stakes, and backstopped by rules and the editor. The founder approved local models for routine work, hosted Haiku for low-cost tasks, Sonnet where quality matters, and a **$35/month** cap with graduated controls.

### Verified provider facts (official pages, read 2026-11-07)
- **Prices**, from [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), per million input/output tokens:
  - Claude Haiku 5.5: **$0.10 / $0.50** for prompts up to 100,000 tokens; **$0.50 / $2.50** for longer prompts, with the higher price applying to the whole request.
  - Claude Sonnet 5.5: **$2 / $10**.
  - Claude Opus 5.5: **$4 / $20**.
- **Batch API:** a 50% discount on input and output tokens.
- **Cache-hit prices:** Haiku 5.5 $0.01, Sonnet 5.5 $0.10, Opus 5.5 $0.20. Caching savings are **not counted** in the estimates below.
- **Structured outputs:** JSON-schema output through `output_config.format` ([structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)). The page's supported-models list includes `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5`.
- **Ollama:** its `format` field accepts a JSON schema ([Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)).
- **Not yet verified:**
  - the `keep_alive` / model-unload setting (V-06);
  - whether the candidate local models fit and perform on a 16 GB M5 (V-07).
  Both are checked in P1-09 and P2-17.

### Routing table (approved allocation)
**Token volumes are assumptions until measured.** They are replaced with `usage_ledger` actuals after P1-09 and the first 10 automated editions.

| Task | Volume per edition (**assumed**) | Stakes | Tier → model | Fallback | Est. $ per edition |
|---|---|---|---|---|---:|
| T1 Scope, category and entity tagging per ingested item | ≈ 120 items × 0.8k in / 0.1k out | Low (rules + editor backstop) | **local** (Ollama, ~8B-class) | Haiku 5.5 on failure or invalid output | 0 (fallback ≈ 0.016) |
| T2 Same-event (duplicate) adjudication | ≤ 20 × 0.6k | Low–medium | **local** | Haiku 5.5 | 0 (≈ 0.001) |
| T3 Injection pre-screen | — | — | Code heuristic, no LLM | — | 0 |
| T4 Ranking suggestions (triage sub-scores) | ≈ 40 × 1.5k in / 0.2k out | Medium (the editor selects) | **Haiku 5.5**; daytime items through the Batch API, the final hour synchronous | local | ≈ 0.007 |
| T5 Claim extraction + evidence excerpts | ≈ 10 × 8k in / 1.2k out | **High** | **Sonnet 5.5** | Fallback vendor for outages only | ≈ 0.28 |
| T6 Script, page copy and caption | 15k in / 4k out | **High** | **Sonnet 5.5** | — | ≈ 0.07 |
| T7 Second-pass verification (critic: script vs verified claims) | 12k in / 1.5k out | High | **Sonnet 5.5** | Haiku only under the budget ladder | ≈ 0.04 |
| Repairs (≈ 20% of T5–T7, **assumed**) | — | — | Same tier | — | ≈ 0.08 |
| T8 LLM regression set (weekly + on any change) | 20 stories | — | Sonnet through the Batch API | — | ≈ $1.8 / month |
| **Opus 5.5** | — | — | **Evaluation and testing only** (P1-09 bake-off, quarterly comparison on the regression set). **Never in the production routing** | — | Evaluation runs only, ≈ $1–3 per run |

**Haiku guard:** Haiku prompts must stay under 100k tokens so they aren't billed at the long-context price. The router rejects larger T4 prompts.

### Monthly API estimate (production routing, assumptions as above)
| Cadence | $ / month | ≈ ₹ @ 88 | vs $35 cap |
|---|---:|---:|---|
| 5 editions/week (≈ 22 editions), approved soft-launch cadence | ≈ $12.4 | ≈ ₹1,090 | 35% |
| 30 editions/month (if a daily cadence is decided later) | ≈ $16 | ≈ ₹1,430 | 46% |
| Development and replay testing while Phase 3 is built (**assumed**) | ≈ $5 | ≈ ₹440 | — |

**Opus for production (not approved).** If evaluations show **≥ 10 percentage points higher claim precision** (a claim fully supported by its cited excerpt) **or ≥ 50% fewer unsupported claims** than Sonnet on the frozen 20-story set, a written proposal goes to the founder with the measured cost difference (Opus for T5 at 22 editions ≈ +$7/month, by the assumed volumes). It is never switched on automatically.

### The local tier must earn its place
Local inference is **not kept for architectural purity.** At Haiku prices, T1 and T2 on Haiku would cost **≈ $0.4/month** at 22 editions, so the local tier's case rests on resilience (it works during API outages or once the cap is hit) and on per-item volume growing with sources. It is benchmarked in P1-09 (offline) and over the Phase 2 window (P2-17). It is **retained only if all four criteria hold**; otherwise T1 and T2 route to Haiku through config, with no code change:

| Criterion | Pass threshold |
|---|---|
| Quality | ≥ 95% agreement with Haiku on T1 scope and category labels; T2 same-event F1 within 5 points of Haiku on the labelled set (P2-08) |
| Latency | Cutoff batch (≈ 120 items) finishes in ≤ 10 min; per-item p95 ≤ 5 s; the model is never loaded during the render window |
| Operational reliability | Local failures plus invalid outputs (schema-validation failures) ≤ 2% of calls over the Phase 2 window; each one falls back to Haiku automatically and is logged |
| Actual cost | API savings measured from `usage_ledger` (fallback rate × Haiku price) compared with the founder's local-tier maintenance time. That time is assumed at ≤ 1 h/month and logged; if it exceeds 2 h/month in two consecutive months, route to Haiku |

**Fallback rule:** if local inference errors, times out (> 15 s) or returns output that fails the JSON schema, the same request goes to Haiku 5.5 once. Both attempts are logged (`usage_ledger.tier`).

**Cost categories:**
- **API costs** are the only LLM cash cost. They are counted in [STRATEGY §6](IMPLEMENTATION_STRATEGY.md#6-cost-model).
- **Local inference** runs on the founder's existing Mac. Hardware is already owned, so there is no incremental capital cost. **Electricity is not measured and not modelled.** It is expected to be small, but it isn't zero and isn't claimed to be zero. **Maintenance** (model pulls, version pinning, troubleshooting) is founder operations time, counted in the review and operations hours.

### Budget ladder (graduated controls, enforced in `brief/llm/budget.py` against `usage_ledger`)
| Month-to-date spend | Action |
|---|---|
| ≥ 80% of the monthly cap | Alert; T7 critic → Haiku; evaluation runs (Opus, ad-hoc comparisons) paused |
| ≥ 95% | T4 → local; T5 only for selected stories (no alternates) |
| 100% (or the daily cap of $1.50) | All paid calls blocked and logged `blocked_by_budget`; the editor writes or edits copy by hand; the local tier continues |

**Caps per budget period** (approved at sign-off on 2026-11-07; defined in `config/budget_periods.yaml` by **plan window, not calendar month**, so caps match the cash model one-to-one):

| Period | LLM cap | Voice cap | Notes |
|---|---:|---:|---|
| Preparation (Day −18 to 0) | $7 (LLM bake-off) | $8 (voice bake-off) | Counted in the one-time line; vendor spend limits as a backstop |
| Days 1–30 | **$10** | **$10** | Drafting only (experiment + early soft launch) |
| Days 31–60 | **$20 interim (PD-02)** | $10 | Phase 3 development and replay testing |
| Days 61–90 | **$35** (approved maximum) | $10 | Automated pipeline running |
| After Day 90 | $35 | $10 (PD-07 review) | Always subject to the cash ceiling in force |

- The daily cap stays at $1.50.
- Every cap is subject to the **₹15,000 ceiling**: `brief cost report` blocks optional spend when the projected max (actual + remaining caps) would exceed it.
- The **voice cap stays at $10** until the vendor comparison is done. A $5 cap is reconsidered only after measured usage (PD-07, P1-39).

**Interface (unchanged):** `brief/llm/client.py` exposes `complete_structured(task, prompt_version, inputs, schema)`. The router reads `config/llm_routes.yaml`. Every response is validated with pydantic after the provider's structured-output constraint, with at most one bounded repair. `stop_reason` (including `refusal`) is checked before content is read. A content refusal is never retried on another vendor without review.

**Alternatives considered:**
- API for everything: simplest, but no outage or cap resilience for routine tasks.
- Local-primary including extraction: weaker strict extraction on ~8B models would raise editor verification time, the most expensive resource.
- Haiku for everything: about $1.5/month, but only if measured parity on extraction, which is not assumed.
- Opus in production: not approved, and would need evidence plus a founder decision.

<a id="adr-004"></a>
## ADR-004 — TTS: API primary, hash cache, Kokoro fallback
**Status:** Accepted (founder choice). Vendor is **Open** until the P1-05 bake-off.
**Decision:**
- `brief/tts/client.py` is a provider interface. Narration is synthesised **per story segment**. Each segment is cached by `sha256(provider‖model‖voice‖settings‖text)` (`media_assets.cache_key`), so a re-render after a small edit only re-synthesises the changed segment.
- A pronunciation lexicon (`video_templates/lexicon.yaml`) maps tricky AI names to provider-specific SSML or respellings.
- Kokoro-82M (Apache-2.0 weights, commercial use permitted per the model card) is the offline fallback.
**Bake-off entrants (P1-05):**
- OpenAI `gpt-4o-mini-tts`
- Google Cloud TTS (Neural2 / Chirp 3 HD)
- ElevenLabs Flash
- Azure Neural
- Kokoro

**Criteria:** AI-name pronunciation (20-term test list), naturalness, commercial-use terms, word/segment timestamps, latency and price.
**Cost:** a 90 s script is about 1,300 characters, so roughly 40k characters a month. At $15–$30 per million characters *(verify per vendor)* that is under $2/month; ElevenLabs might reach ~$4–8 at the quoted rates. Cap: `TTS_MONTHLY_BUDGET_USD = 10`.

<a id="adr-005"></a>
## ADR-005 — Render on the Mac worker; cutoff at 17:00
**Status:** Accepted (provisional; revisit after 30 editions).
**Context:** The founder allowed "Mac worker or render API; schedule earlier if the cutoff is strict." The M5 renders a 90 s 1080×1920 video in well under 5 minutes (to be confirmed in P1-10).
**Decision:** a `heavy` queue served only by the Mac worker (launchd, `caffeinate` during 16:30–20:30). Cutoff moves to 17:00 IST. If the worker heartbeat is missing at 16:45, the editor is alerted.
**Revisit trigger:** two or more Reels missed in a month because the Mac was unavailable. Then move the heavy queue to an on-demand cloud VM, or a container on a bigger VPS (the same `brief worker` image). That needs no code change, because the worker is location-agnostic.
**Rejected for now:** paid render APIs and generative video. They cost more, and the card-based format doesn't need them.

<a id="adr-006"></a>
## ADR-006 — Static site generated by Python (Jinja), deployed with wrangler
**Status:** Accepted.
**Decision:**
- `brief site build` renders `site_templates/` into `dist/` with `/today/` (a meta refresh + canonical link + `_redirects` 302 to the current issue), `/issues/YYYY-MM-DD/`, `/archive/`, `/topics/<slug>/`, `/companies/<slug>/`, `/sources/<slug>/`, `/corrections/`, policy pages, `sitemap.xml`, `feed.xml` (RSS of issues) and `search-index.json`.
- Archive filtering (date, topic, company, source) is a small vanilla JS over `search-index.json`. At about 2 KB per issue that stays small for years.
- Deploys use `wrangler pages deploy` direct upload. Previews use a branch alias.
- JSON-LD `NewsArticle` per story and `CollectionPage` per issue. No thin pages: topic and company pages exist only once they have 3 or more stories.
**Alternatives:** Astro or Hugo (another toolchain), or Pagefind for full-text search (can be added later as a post-build step if users ask for it).
**Facts *(verify)*:** the Pages free plan allows 500 builds/month and one concurrent build; static requests and bandwidth are unlimited. Direct uploads don't use Pages' build system, but confirm how they are counted in P1-12.

<a id="adr-007"></a>
## ADR-007 — Job queue in Postgres (`FOR UPDATE SKIP LOCKED`)
**Status:** Accepted.
**Decision:** one `jobs` table with leases, an idempotency key, backoff and a `dead` state, plus a transactional `outbox_events` table that n8n polls.
**Alternatives:**
- Redis + RQ/Celery: one more service to run.
- Supabase `pgmq`: viable, but less portable.
- n8n queue mode: puts logic in n8n.

At about 100 jobs a day, Postgres is far more than enough.

<a id="adr-008"></a>
## ADR-008 — No pgvector in the MVP
**Status:** Accepted.
**Decision:** clustering uses canonical URLs, content hashes, shared primary links, `pg_trgm` title similarity plus entity overlap, and capped LLM adjudication of borderline pairs.
**Revisit trigger:** in the P2-08 evaluation, clustering misses more than 10% of true duplicates on a labelled 2-week sample. Then add embeddings (pgvector on Supabase) for the 72 h window only.

<a id="adr-009"></a>
## ADR-009 — Phase 1 uses JSON files, not a database
**Status:** Accepted.
**Decision:** each edition is `editions/YYYY-MM-DD.json`, validated by a JSON Schema generated from pydantic models. Its shape mirrors the database ([DATABASE_DESIGN §7](DATABASE_DESIGN.md#7-edition-json-phase-1-file-format--daily_issuesedition_json)), and `brief issue import` loads it in Phase 2.
**Why:** Phase 1 tests editorial value and production time. Infrastructure would add cost before the format is proven.

<a id="adr-010"></a>
## ADR-010 — Email: hosted provider is the system of record
**Status:** Open (default: decide in P7-01).
**Decision direction:** the provider handles double opt-in, unsubscribe, bounce handling and consent records, and we store only aggregates. The signup form on the static site posts directly to the provider's hosted form or embed, so our infrastructure has no PII.
**Candidates and current facts *(conflicting sources, verify)*:**
- **MailerLite**: free plan about 250 subscribers (recently reduced), with branding.
- **Brevo**: free plan stores up to 100k contacts but sends only **300 emails/day**, which caps a daily send at 300 subscribers.
- **Buttondown**: free tier reported at 100 or 1,000 subscribers; developer-friendly API and Markdown.

**Criteria:** API to create and send a campaign per issue, double opt-in, custom domain authentication (SPF/DKIM/DMARC), India billing, export, and cost at 1k/5k/10k subscribers.

<a id="adr-011"></a>
## ADR-011 — Instagram API with Instagram Login
**Status:** Open (default: Instagram Login; confirm in P6-01).
**Facts (Meta docs, checked 2026-11-07):**
- Reels publish via a `media_type=REELS` container, then `status_code` polling (`IN_PROGRESS`, `FINISHED`, `ERROR`, `EXPIRED`, `PUBLISHED`), then `media_publish`.
- Containers expire after 24 h.
- Polling is recommended once per minute for at most 5 minutes.
- The video must be at a public URL.
- The API publishing limit is stated as **100 posts per 24 h** on one Meta page and **50** on another *(verify; irrelevant at 1 post/day, but always check `content_publishing_limit`)*. There is also a 400 containers per 24 h limit.
- Long-lived tokens last 60 days and can be refreshed once they are 24 h old and not yet expired.
- The permissions are `instagram_business_basic` and `instagram_business_content_publish`.

**Decision:** an Instagram Professional (Creator or Business) account, using the Instagram Login flow (no Facebook Page needed). The token is stored encrypted in the database and refreshed daily when due. Only `brief publish` calls the API.
**Alternative:** Facebook Login for Business, which needs a linked Page and gives more insights options. Choose this if the insights metrics needed in Phase 7 require it.

<a id="adr-012"></a>
## ADR-012 — Split state machines; preview before public
**Status:** Accepted.
**Decision:** the four state machines are defined in [SYSTEM_ARCHITECTURE §6](SYSTEM_ARCHITECTURE.md#6-state-machines). The issue page is deployed to a **preview** alias for review. Production deploy (`site_live`) happens only after `approved`, and the Reel only after `site_live` returns HTTP 200. CLAUDE.md is updated to match.
**Why:** the business plan published the page before the quality gate, which could expose unreviewed claims. A preview gives the reviewer the real rendered page with no public exposure.

<a id="adr-013"></a>
## ADR-013 — Secrets management
**Status:** Accepted.
**Decision:**
- Local: `.env` (git-ignored, `chmod 600`), loaded by pydantic-settings, with `.env.example` committed.
- VPS: Docker secrets or env files with `0600` permissions; n8n credentials in n8n's encrypted store (`N8N_ENCRYPTION_KEY` backed up offline).
- The Instagram token is `pgp_sym_encrypt`ed in `platform_tokens`, with the key only in the worker environment.
- Every provider token is scoped to the minimum (Cloudflare: Pages Edit on one project plus R2 object read/write on two buckets; GitHub: fine-grained, public read).
- A pre-commit `gitleaks` hook.

**Optional later:** 1Password CLI or Doppler. Not needed for one operator.

<a id="adr-014"></a>
## ADR-014 — Apify: research via MCP, production via fixed Actor calls
**Status:** Accepted.
**Decision:**
- Apify MCP is used only in human-driven sessions to evaluate Actors (notes go in `research/apify/`).
- Production uses the Apify REST API with `APIFY_ALLOWED_ACTORS` (code allow-list), fixed `apify_input` per source, `maxItems` caps, per-run `APIFY_MAX_RUN_USD` and logged run and dataset IDs.
- The MVP may have **zero** Actors if feeds and APIs cover the allow-list. Apify is introduced only for a named tier-1 source that has no feed.
**Facts *(verify)*:** the free plan includes **$5/month** usage credit and blocks rather than bills overage. Starter was reported cut from $29 to **$19/month** in Sept 2026.

<a id="adr-015"></a>
## ADR-015 — Video: Pillow cards + FFmpeg, burned-in subtitles
**Status:** Accepted.
**Decision:**
- Each story card is a 1080×1920 PNG rendered by Pillow (headline, publisher, date, category chip, key phrase).
- Simple motion is done in FFmpeg filters (Ken Burns zoom, crossfades, progress bar).
- Subtitles are ASS files burned in. Timing comes from segment durations (ffprobe), split into phrase chunks proportional to characters, or from provider word timestamps when available. No speech-to-text.
- Output: H.264 High, 30 fps, AAC 48 kHz, −14 LUFS loudness, 60–90 s, with a cover frame exported.
- Fonts: OFL-licensed (e.g. Inter, Noto) stored in the repo with their licences.
- Music: none in the MVP, or one licensed track recorded in `media_assets.license`.
- No company logos or product screenshots unless the rights are documented.

**Rejected:** browser/Remotion rendering (heavier toolchain) and generative video (cost, plus the risk of misleading visuals).
**Open item found at setup (2026-11-08):** the standard Homebrew FFmpeg 9.0.2 has no `ass`/`subtitles` filter (no libass), so burning in ASS subtitles needs `ffmpeg-full`. The recommended alternative is to render subtitle chunks as transparent PNGs with Pillow and overlay them with timed FFmpeg `overlay` filters. That adds no dependency and stays deterministic. Decided in P1-08.

<a id="adr-017"></a>
## ADR-017 — Public soft launch at 5 editions a week after a passed experiment
**Status:** **Approved 2026-11-07** (founder): 5 editions a week, starting only if the validation experiment passes. **PD-04 approved:** whether to return to 7 editions a week is decided **only at the Day-90 review (G9)**. The 5-edition cadence does not change before then.
**Context:** Publishing daily while building Phases 2–4 would add about 15–17 h/month of editorial work over the 5-a-week cadence, and would slow the automation build. Publishing nothing until automation is ready would leave the 90-day review without audience evidence.
**Decision:**
- **Gate G3 (experiment) = continue, then gate G4 (soft-launch readiness)**, which requires: the final name, handle and domain (P0-05); the Instagram Professional account (P1-15); minimal policy pages (P1-20 / P1-20U); and `noindex` removed. **Then** public editions start on **Mon–Fri**, target Day 15, uploaded by hand with the Phase 1 toolkit plus any automation that has passed its gate.
- The cutoff is 17:00 IST and the target publishing time 20:00 IST, both approved.
- Full review applies to the first 30 manual public editions (EDITORIAL_PIPELINE §9).
- A pivot at G3 shifts the soft launch by at least 7 days per pivot. A stop cancels it.

**Expected volume:** about 55 public editions by Day 90 if there is no pivot (Days 15–30 ≈ 11, 31–60 ≈ 22, 61–90 ≈ 22).
**Consequences:**
- The brand says "weekday AI brief".
- **Monday edition (PD-06 approved):** Monday may include important Saturday and Sunday developments. Rubric v1.1 scores freshness against the edition window (Fri 17:00 → Mon 17:00), so important weekend stories are not penalised for happening or being published earlier. Event date and publication date are always shown separately ([EDITORIAL_PIPELINE §5.2](EDITORIAL_PIPELINE.md#52-edition-window-and-weekend-stories-rubric-v11-pd-06)).
- Scheduling: WF-02 (cutoff) and WF-06 (publish) run on publishing days only (`PUBLISH_DAYS = Mon–Fri`). Ingestion runs every day.

<a id="adr-016"></a>
## ADR-016 — Testing strategy
**Status:** Accepted.
**Decision:**
- pytest unit tests for normalisation, rules, scoring and state transitions.
- **Golden-file tests**: fixture editions → expected validation results, card PNG hashes (tolerance-based) and an ffprobe manifest.
- HTTP tests use recorded cassettes (`pytest-recording`), with no live calls in CI.
- An **LLM regression set**: 20 frozen stories with expected claims, scored by rules (URL subset, excerpt substring, claim-type accuracy). It runs on every prompt or model change.
- A DB integration suite runs against a local Postgres in Docker, covering migrations, triggers and the queue claim under concurrency.
- A Meta API contract test uses a sandbox or test account before going live.
- CI: GitHub Actions running ruff, mypy and pytest. No secrets in CI except a test-only budget-capped LLM key for an optional nightly regression.
