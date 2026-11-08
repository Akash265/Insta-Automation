# Risks and Operations — AI Daily Brief

Status: **Planning baseline v1** (2026-11-07).
Related: [SYSTEM_ARCHITECTURE](SYSTEM_ARCHITECTURE.md) · [WORKFLOWS](WORKFLOWS.md) · [EDITORIAL_PIPELINE](EDITORIAL_PIPELINE.md) · [TECHNICAL_DECISIONS](TECHNICAL_DECISIONS.md)

This is operational guidance, not legal advice. Platform, privacy and advertising rules need checking against current official sources before launch.

## 1. Risk register

L = likelihood, I = impact (H/M/L).

| # | Risk | L | I | Mitigation | Early warning | Owner |
|---|---|---|---|---|---|---|
| R1 | A false or exaggerated AI claim is published | M | H | Claim-to-evidence mapping, C-checks, human approval of every edition; full review of the first 30 manual and first 30 automated editions, the 10 editions after any material error, and high-risk stories; an independent auditor; a corrections process | `contested` claims; C05 warnings; corrections KPI | Editor |
| R2 | Stale news presented as new | H | M | Separate `event_at`, freshness scoring, R03 and R12 | Share of rejected R03 items | Editor |
| R3 | The same story repeated across days | H | M | Clusters, R07, a 7-day covered window | Editor overrides of R07 | Eng |
| R4 | A Reel is published twice | L | H | Unique constraints, `max_attempts=1`, reconciliation by `issue_key` | Any `needs_reconciliation` | Eng |
| R5 | Instagram token or permission failure | M | H | Daily refresh check, alert at 7 days before expiry, publisher stops while the queue is kept | `v_token_status` | Eng |
| R6 | Meta API or policy changes | M | H | `api_version` pinned and logged, quarterly docs review, manual upload fallback | Container `ERROR` rate | Eng |
| R7 | Mac unavailable at cutoff | M | M | Heartbeat alert at 16:45, `caffeinate`, render-elsewhere plan ([ADR-005](TECHNICAL_DECISIONS.md#adr-005)) | Heartbeat gaps | Founder |
| R8 | API cost overrun (LLM, TTS, Apify) | L | M | Hard caps in code, an 80% warning, ledger review in the weekly report | `usage_ledger` totals | Founder |
| R9 | Prompt injection via scraped text | M | M | Data-only prompts, no tools, schema output, URL and excerpt subset checks, injection flag | `injection_suspect` flags | Eng |
| R10 | Copyright or asset-licence breach | M | H | Original narration, R09 n-gram check, licence field required on every asset, no third-party logos or screenshots without rights | Assets with an empty `license` (blocked) | Editor |
| R11 | Scraping terms or robots violation | M | M | Feeds and APIs first; per-source terms check in P1-01; Apify allow-list; no auth bypass | Source review notes | Founder |
| R12 | Secret leak (repo, logs, n8n) | L | H | gitleaks, log scrubbing, scoped tokens, encrypted IG token, n8n behind auth and an IP allow-list | gitleaks CI; access logs | Eng |
| R13 | Supabase free tier limits (pausing, no backups) | M | M | Daily activity keeps the project live; own nightly dumps; weekly restore test; Pro at launch | Backup job failures | Eng |
| R14 | Founder time exceeds 2.5 h per edition | H | H | Time logged per step; automate only steps that are measured bottlenecks; quiet-day policy | `production_log` and audit durations | Founder |
| R15 | Generic "AI slop" perception hurts reach and trust | M | H | Original "why it matters", restraint, sources shown, no filler | Retention and saves trends | Editor |
| R16 | Undisclosed commercial content | L | H | C11, sponsor register, ASCI-style labels | — | Founder |
| R17 | Email consent or privacy problem | L | H | Provider-hosted double opt-in, privacy notice, no PII in our DB | Complaint rate | Founder |
| R18 | Single-platform dependency | H | M | Owned site + email; portable JSON; cross-posting only after 10 consecutive reconciled runs | — | Founder |
| R19 | Review fatigue: approvals become rubber stamps once automation is good | M | H | Flagged items first, each needing an explicit check; permanent weekly deep audit of 2 stories; "review too fast" note; any material error returns the next 10 editions to full review ([EDITORIAL_PIPELINE §13.3](EDITORIAL_PIPELINE.md#133-guarding-against-rubber-stamping)) | Review durations; audit findings | Editor |
| R20 | Local-model problems: memory contention with FFmpeg on 16 GB, quality drift after model updates | M | L | Only two low-stakes tasks; Haiku fallback; the model is unloaded after use and never runs during the render window; version pinned; regression on the labelled set before any model change | Fallback rate in `usage_ledger` | Eng |
| R21 | Soft launch overloads the founder (editorial + build) or exposes a weak format | M | M | 5 editions a week (approved); only after a passed experiment and gate G4; weekly hours tracked against STRATEGY §6.5. Any cadence change needs a founder decision | Weekly founder hours | Founder |
| R22 | The volunteer auditor is unavailable on many days, so audit coverage falls | M | M | Coverage target ≥ 10 of 14 editions; self-audits marked and reported separately as weaker; pre-publication checks are optional; recruit a backup volunteer if coverage drops below 70% in week 1 | Audit coverage in `audit-log.csv` | Founder |
| R23 | A small, friendly panel is over-interpreted as demand | H | M | 3.8/5 is labelled an early qualitative signal; distributions and per-panelist medians are reported; no population claims; demand is tested in the soft launch and at G9 | Gate document wording | Founder |
| R24 | Schedule compression: Days 31–60 hold about 29 engineering days of scope plus editorial work (about 32 h/week) | H | M | Gates, not dates; Phase 2 starts in Days 15–30; if weekly hours exceed plan by > 20% for 2 weeks, engineering scope moves later. Editorial quality, review and cadence are never cut to save time | Weekly hours; task slip | Founder |
| R25 | The local TTS engine fails on quality, pronunciation or speed, or a voice licence proves non-commercial | M | M | P1-05 benchmark with hard licence gate; an alternative engine behind the same interface; pronunciation lexicon; paid fallback available but off; never use a voice without a commercial-use licence record | Benchmark results; review flags | Founder |

## 2. Facts to re-verify before relying on them

**Status key:**
- **Verified (official)** means read on the provider's own documentation page, with the date given.
- **Unverified** means the figure comes from secondary sources or memory and must not be treated as confirmed.

Each item has a V-ID in the [TASKS.md verification tracker](../TASKS.md#f-verification-tracker). Record the verified value, the source URL and the date in the relevant ADR.

| V-ID | Fact | Current understanding | Status | Verify in |
|---|---|---|---|---|
| V-01 | Anthropic model names and base prices | Haiku 5.5 $0.10/$0.50 (≤ 100k-token prompts; $0.50/$2.50 above); Sonnet 5.5 $2/$10; Opus 5.5 $4/$20 per million tokens | **Verified (official)** 2026-11-07, platform.claude.com pricing | Re-check at P3-01 |
| V-02 | Anthropic Batch API discount | 50% on input and output | **Verified (official)** 2026-11-07 | — |
| V-03 | Anthropic cache-hit prices | Haiku 5.5 $0.01, Sonnet 5.5 $0.10, Opus 5.5 $0.20 per million tokens (not used in estimates) | **Verified (official)** 2026-11-07 | — |
| V-04 | Structured outputs (JSON schema) on Haiku 5.5 and Sonnet 5.5 | `output_config.format`; both models listed as supported | **Verified (official)** 2026-11-07 | Re-check at P1-09 |
| V-05 | Ollama JSON-schema output | `format` accepts a JSON schema | **Verified (official)** 2026-11-07, docs.ollama.com | — |
| V-06 | Ollama model unload / `keep_alive` setting | Not stated on the page read | Unverified | P2-17 |
| V-07 | Local model fit and quality on a 16 GB M5 (`gemma4:e4b`, `qwen2.5:7b`) | Secondary sources say ~8B at 4-bit fits | Unverified (measure) | P1-09, P2-17 |
| V-08 | Paid TTS vendor prices and terms (optional fallback only) | Aggregator figures only; relevant only if the paid fallback is approved | Unverified | Only if the fallback is needed |
| V-09 | Kokoro licences | Code Apache-2.0 (LICENSE file); weights Apache-2.0, permissive training data (model card) | **Verified (official)** 2026-11-08 | Re-check at P1-05 |
| V-23 | espeak-ng licence (used by Kokoro and Piper) | Believed GPL; affects distributing software, not audio | Unverified | P1-05 |
| V-24 | Piper `en_GB-cori-medium` commercial use | Voice dataset public domain (LibriVox; model card). Piper docs say "intended for personal use and text to speech research only" | Unverified; needs review | P1-05 |
| V-10 | Domain price | ₹1,000–2,500 a year (business plan) | Unverified | P0-05 |
| V-11 | Cloudflare Pages limits (direct uploads) and R2 free tier | 500 builds/month; R2 10 GB-month, 1M Class A, 10M Class B, no egress fees, **no hard spend cap** | Unverified (seen only in search summaries) | P1-12 |
| V-12 | Supabase Free limits, backups, pausing; Pro price | 7-day inactivity pause; backups not reliably included; Pro $25/month | Unverified | P2-01 |
| V-13 | Hetzner entry VPS price | About €3.5–4.5/month after the 2026 changes; CX22 may be replaced by CX23 | Unverified | P2-12 |
| V-14 | healthchecks.io free plan | Hobbyist: 20 checks; Telegram integration | Unverified | P2-13 |
| V-15 | GitHub Free private repos and Actions minutes | Free private repos; minute allowance unknown | Unverified | P0-04 |
| V-16 | Apify free credit and Starter price | $5/month credit; Starter $19 (was $29) | Unverified | P2-10 |
| V-17 | n8n licence fit for internal use | Sustainable Use License | Unverified | P2-12 |
| V-18 | Instagram API publishing limit, container polling and expiry, caption editing, presigned `video_url` | 100 or 50 posts per 24 h (Meta pages disagree); poll once a minute for up to 5 min; 24 h expiry; others unknown | Unverified | P6-01, P6-02 |
| V-19 | Long-lived IG token lifetime and refresh | 60 days; refreshable once 24 h old | Unverified | P6-03 |
| V-20 | Email provider free tiers | MailerLite ~250; Brevo 300/day; Buttondown 100 or 1,000 | Unverified | P7-01 |
| V-21 | ASCI / CCPA disclosure wording | Latest guidance | Unverified | P8-02 |
| V-22 | India DPDP Act obligations for a newsletter list | Get professional advice | Unverified | P7-02 |

## 3. Security controls

### 3.1 Secrets
See [ADR-013](TECHNICAL_DECISIONS.md#adr-013). Rules:
- Secrets are never placed in the repo, in job payloads, in `audit_logs.details`, in outbox events or in n8n workflow JSON.
- `brief/logging.py` scrubs any value whose key matches `(?i)(token|secret|key|password|authorization)`. Every exception message is passed through the scrubber before it is stored.
- Rotate secrets on suspicion and every 6 months. The IG token rotates itself through refresh.

### 3.2 Least-privilege matrix

| Principal | Can | Cannot |
|---|---|---|
| `brief_app` (worker/CLI) | DML on app tables; INSERT only on append-only tables | DDL; UPDATE/DELETE on audit, corrections or reviews |
| `brief_n8n` | EXECUTE `brief_*` functions; SELECT `v_*` views | Read or write tables directly; read `platform_tokens` |
| `brief_backup` | SELECT all (pg_dump) | Any write |
| Supabase anon / authenticated | Nothing (RLS deny-all) | — |
| Cloudflare API token | Pages Edit (1 project); R2 Object R/W (2 buckets) | DNS, Workers, account settings |
| Apify token | Run allow-listed Actors (enforced in code); spend capped per run | — |
| GitHub token | Public repo read | Write |
| Meta app | `instagram_business_basic`, `instagram_business_content_publish` (+ insights in Phase 7) | Comments, DMs, any interaction automation (out of scope by policy) |

### 3.3 Database
- SSL is required. Database passwords are strong and unique. Supabase network restrictions limit access to the VPS IP and home IP where practical.
- RLS is enabled with no policies, and the Data API is not used for app tables.
- Migrations are reviewed in PRs. The service-role credential is used only to run migrations and is never stored on the worker.

### 3.4 R2 buckets

| Bucket | Visibility | Contents |
|---|---|---|
| `brief-public` | Public via a custom domain (`media.<domain>`) | **Only after go-live:** cover/OG images and, if the presigned approach fails, the final MP4 under `reels/<issue_key>-<128-bit random>.mp4` |
| `brief-private` | Private | Source snapshots, TTS segments, intermediate renders, the final MP4 (canonical copy), DB backups |

- **The MP4 goes to Meta through a presigned GET URL** (24 h expiry) generated at publish time, so nothing is public before approval. If P6-02 shows Meta rejects presigned URLs, fall back to copying the MP4 to `brief-public` with an unguessable key **only after `approved`**.
- R2 has no hard spend cap, so a weekly usage check runs in WF-13 and lifecycle rules follow [DATABASE_DESIGN §9](DATABASE_DESIGN.md#9-retention-summary).

### 3.5 n8n host
- Caddy provides TLS. The n8n editor sits behind Cloudflare Access or an IP allow-list, and n8n user accounts have MFA where supported.
- `N8N_ENCRYPTION_KEY` is backed up offline. Unattended security upgrades are on and the n8n image tag is pinned (updated monthly after reading release notes). The firewall allows 22 (key-only SSH) and 443 only.
- Community nodes are not installed unless reviewed.

### 3.6 Untrusted content
See [EDITORIAL_PIPELINE §8](EDITORIAL_PIPELINE.md#8-llm-safety-and-prompt-injection-handling). Additional controls:
- Fetchers use 2 MB and 15 s limits, allow only `https`, block private IP ranges (SSRF guard: resolve DNS and reject RFC1918, loopback and link-local), parse XML with entity expansion disabled, and never execute JavaScript.
- Site templates autoescape all text. Scraped HTML is never rendered on the site.

## 4. Cost controls

| Provider | Cap (start) | Enforcement | Warn at |
|---|---|---|---|
| LLM | $1.50/day; per plan window (approved): **$7** preparation bake-off · **$10** Days 1–30 · **$20** Days 31–60 (PD-02) · **$35** Days 61–90; plus the [budget ladder](TECHNICAL_DECISIONS.md#adr-003) | `brief/llm/budget.py` checks `usage_ledger` before each call; blocked calls are logged with status `blocked_by_budget` | 80% (WF-09) |
| TTS | **₹0 expected** (local engines). Contingency caps kept until local testing succeeds: **$8** preparation, **$10** per window (PD-07); P1-39 reconsiders | Same pattern; the paid fallback is off by default | 80% |
| Apify | Free plan ($5 credit); $0.50 per run | Code allow-list + `maxItems`; the free plan blocks at its limit | 80% of credit |
| R2 | Expected $0 | Lifecycle rules; weekly usage check | 8 GB stored |
| Supabase | Free through Day 90 → Pro ($25, unverified) at the Phase 5 gate (OD-04, proposed) | Plan choice | DB size 400 MB |
| VPS | Fixed monthly | — | — |

Any new paid subscription needs a written note in the weekly review (business plan budget policy). **The 90-day cash ceiling is ₹15,000 (approved).** Optional spend is frozen if actual spend passes ₹10,000 before Day 60 ([STRATEGY §6.7](IMPLEMENTATION_STRATEGY.md#67-90-day-totals-vs-the-15000-ceiling)).

## 5. Reliability: retries and dead letters

- Retries are bounded (at most 3) with exponential backoff and jitter, and are applied only to `RetryableError` ([WORKFLOWS §2](WORKFLOWS.md#2-job-types)).
- Non-idempotent external actions (`media_publish`, the email campaign send) have `max_attempts = 1` and go through reconciliation.
- Every `dead` job raises an alert. Dead jobs are kept 180 days for analysis, and the retry command requires a reason.
- Every external call goes through `httpx` with explicit timeouts (connect 5 s, read 30 s; 120 s for Apify and TTS).

## 6. Recovery runbooks

Each runbook ends with the issue in an explicit state (never stuck in a silent "in-progress") and an `audit_logs` row.

| Failure | Detection | Automatic response | Operator action |
|---|---|---|---|
| A source feed fails | `source_fetch_runs.failed`; 10 consecutive failures | Retry next interval; auto-disable at 10 + alert | Fix the URL, replace the source, or accept the loss; re-enable |
| Ingestion broadly down (network, DB) | WF-09: no successful fetch in 2 h | Alerts | Check the worker and DB; the manual Phase 1 path remains available |
| No verified stories / quiet day | Fewer than 3 eligible at shortlist | Shortlist form defaults to "Quiet day" options | Choose web-only, short Reel or skip. **Never fabricate filler** |
| Missing evidence for a material claim | C-checks; claim not `supported` | `prepare_issue` holds and lists the gaps | Add evidence, attribute the claim, or drop the story |
| Malformed LLM output | Schema validation fails twice | Job `dead`; issue `held` | Write the copy by hand (form or JSON edit), or retry after a prompt fix (logged) |
| LLM provider outage | 5xx or timeouts | Retry, then the fallback provider (outage only) | If both are down, edit manually |
| LLM budget cap hit | `blocked_by_budget` | Call blocked; alert | Edit manually or raise the cap with a reason |
| TTS error | Local engine error or invalid audio | Retry once, then the next local engine in the chain (Kokoro → Piper); the lexicon still applies | If the voice changed, flag it in review. Use the paid fallback only if the founder has enabled it; otherwise delay the edition |
| Render failure (FFmpeg) | Non-zero exit or ffprobe check fails | Retry once; keep intermediates and the log in private R2 | Inspect the log; re-render; fall back to the last known-good template version |
| Mac offline at cutoff | Heartbeat older than 10 min at 16:45 | Alert | Wake the Mac or run the worker on a backup machine; otherwise the issue is web-only |
| Preview deploy or link check fails | `deploy_preview` dead; C02 fail | Retry; a dead link is retried once | Replace the dead source with an authoritative one or drop the story |
| Production deploy fails / site down | `go_live` dead; HTTP check ≠ 200 | Retry; **the Reel stays blocked** (it needs `site_live`) | Fix the deploy; Cloudflare status check; re-run `go_live` |
| Container `ERROR` | status_code | `publishing_jobs.failed`; alert | Check the video spec (codec, duration, size); re-render; publish manually if needed and record the media id via `brief publish reconcile --manual-media-id` |
| Container `EXPIRED` | status_code | `failed` | Create a new container (new publishing attempt, new idempotency suffix with a reason) |
| Publish timeout / ambiguous result | `AmbiguousError` | `needs_reconciliation` → `reconcile_reel` | If still ambiguous, check Instagram by hand and record the result. **Never blindly re-publish** |
| Token expired or permission revoked | 190/401-class errors | Publisher stops; queue kept; alert | Re-authorise through Meta's login flow; run `brief token store` |
| Rate limit / quota | `content_publishing_limit` / 429 | Back off; alert | Wait; investigate any unexpected usage (possible compromise) |
| Supabase down or paused | Connection errors | Worker backs off; WF-09 alert (n8n also fails to read, so it alerts on its own DB error) | Resume or restore the project; the manual path remains |
| n8n down | External uptime check (free monitor on `/healthz`) | — | Restart the container; run critical steps through the `brief` CLI; the outbox catches up |
| A critical error is published | Reader report or self-review | — | WF-12 correction (critical): fix the page within 4 h, add a clarification, consider removing the Reel |
| Suspected account compromise | Unexpected posts or token use | — | Revoke the app token, rotate secrets, change passwords and enable 2FA, review `audit_logs` |

## 7. Backups and disaster recovery

- **Targets:** RPO 24 h (nightly dump), RTO 4 h for the database. Published pages and MP4s survive a database loss because they live in Pages and R2.
- **Backed up:** `pg_dump -Fc` nightly to `brief-private/backups/daily/` (30 kept) and monthly (12 kept); `editions/*.json` in git; `n8n/` exports in git; `N8N_ENCRYPTION_KEY` and `BRIEF_TOKEN_KEY` stored offline (password manager).
- **Restore drill:** a weekly automated restore into a scratch database with row counts compared (WF-11), and a manual full-recovery rehearsal once before the Phase 5 launch.

## 8. Monitoring, KPIs and review cadence

**Alerts** (WF-09 → WF-10):
- worker heartbeat;
- dead jobs;
- issue past its deadline;
- `needs_reconciliation`;
- token expiry in under 7 days;
- budget above 80%;
- source failing 10 times;
- backup failure;
- n8n uptime;
- HTTP status of `/today`.

**KPIs** (business plan §10). Reported weekly by WF-13 from Phase 3 onward, and by hand from the edition JSON in Phase 1.

| KPI | Definition | Target / use |
|---|---|---|
| Publication reliability | Published ÷ planned (policy skips excluded) | Ops health |
| Material factual error rate | Editions with a material or critical correction ÷ published | Target 0 |
| Source coverage | Selected stories with complete evidence ÷ selected | 100% |
| Research-to-publish time | Cutoff → `published` | Bottleneck finding |
| Founder minutes per edition | From `production_log` or audit | < 150 |
| Cost per edition | Monthly cash ÷ published editions | Unit cost |
| Retention, saves+shares/reach, profile→issue CTR, email conversion | Instagram Insights, site analytics, provider (Phase 7) | Hypotheses until a 30-edition baseline exists |

**Cadence:**
- **Daily:** the editor glances at the publish notification.
- **Weekly (Monday):** WF-13 digest plus the business plan's review agenda (editorial, quality, audience, operations, learning).
- **Monthly:** cost and hours per issue; dependency and n8n updates; Meta changelog review.
- **Quarterly:** continue, pivot or pause decision; re-verify every fact in §2; rotate secrets every 6 months.

## 9. Privacy and consent

- Analytics are cookieless (Cloudflare Web Analytics) and no personal data is kept in our database. The signup form is hosted by or posts directly to the email provider ([ADR-010](TECHNICAL_DECISIONS.md#adr-010)).
- The privacy notice states what is collected (email address, through the provider), why, where it is stored, how long, and how to unsubscribe or request deletion. It is published before signup goes live (P7-02).
- Double opt-in is required. Addresses are never bought, scraped or imported.
- India's DPDP Act 2023 and its rules may apply to subscriber data. Get advice before launching email (Open decision OD-09).
- Source collection avoids personal data. Snapshots are private and pruned after 30 days unless they are evidence.

## 10. Incident response

| Severity | Examples | Response |
|---|---|---|
| SEV1 | Factually harmful critical error published; account compromise; secret leak | Act immediately: contain (remove or clarify, revoke), notify via the public correction note where relevant, postmortem within 48 h |
| SEV2 | Missed Reel; duplicate post; site down during publish window | Same day: restore, and post a transparent delay note if needed |
| SEV3 | Source outage; minor correction; single job failures | Next working session |

**Postmortem template** (`docs/incidents/YYYY-MM-DD-<slug>.md`): timeline, impact, root cause, what worked, what didn't, actions (each becomes a TASKS.md item).

## 11. Compliance checklist (before Phase 5 launch)

- [ ] Every source reviewed for terms and robots, with notes in `sources.notes`.
- [ ] Every visual and audio asset has a licence record; fonts are OFL; no unlicensed logos.
- [ ] Meta app review / permissions approved for the account type; publishing tested on the real account.
- [ ] Privacy notice, editorial standards, corrections policy, contact and about pages are live.
- [ ] Disclosure templates prepared (needed only in Phase 8).
- [ ] Incident contacts and the restore procedure tested.
