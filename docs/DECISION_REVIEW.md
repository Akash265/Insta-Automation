# Decision Review: Proposal and Finalisation

- **Proposal:** 2026-11-07.
- **Finalised:** 2026-11-07, after the founder approved the decisions in §0.
- **Signed off:** 2026-11-07. PD-01 to PD-07 are approved (§7), and the [final sign-off](#10-final-planning-sign-off-2026-11-07) is in §10.
- **Status:** planning only. No application code, dependencies, infrastructure or accounts exist yet. The preparation window starts only on the founder's explicit approval.

**Evidence rule.** A provider fact counts as **verified** only when it was read on the provider's own documentation, as recorded in the [verification tracker](../TASKS.md#f-verification-tracker). On 2026-11-07 that applies to:
- Anthropic model names, prices, the Batch discount, cache prices and structured-output support;
- Ollama's JSON-schema `format`.

Every other price or limit is **unverified** and marked *(verify)*.

## 0. Finalised decisions (2026-11-07)

| Decision | Approved value | Recorded in |
|---|---|---|
| Cash ceiling | **₹15,000** for the first 90 days | STRATEGY §6, TASKS §B |
| Soft-launch cadence | **5 editions a week** | ADR-017 |
| Public soft launch | Starts **only if the validation experiment passes** (target Day 15, after gate G4) | ADR-017, ROADMAP |
| LLM architecture | **Hybrid:** local Ollama (tagging, duplicate detection; hosted fallback) + Haiku 5.5 (ranking suggestions, low-cost tasks) + Sonnet 5.5 (claim extraction, script, second-pass verification). **Opus for evaluation and testing only.** $35/month cap with graduated controls | ADR-003 |
| Local inference | Kept **only if it passes measured quality, latency, reliability and cost benchmarks**; otherwise routed to Haiku | ADR-003 |
| Experiment thresholds | **Approved, fixed before Day 1**, with the clarifications in VALIDATION_EXPERIMENT §3 (none loosens a threshold) | VALIDATION_EXPERIMENT |
| Manual full-review period | **First 30 manual editions** | EDITORIAL_PIPELINE §9 |
| Automated full-review period | **First 30 automated editions** | EDITORIAL_PIPELINE §9 |
| Material-error response | Any material factual error → **the next 10 editions in full review** | EDITORIAL_PIPELINE §9 |
| Human approval | **Mandatory before every publication** in the MVP; no silent publishing | EDITORIAL_PIPELINE §9.1 |
| Founder hourly value | **₹500/h** | STRATEGY §6.5, §6.8 |
| Reader panel | 8–12 participants, **unpaid**; the founder needs recruitment help, so a kit is provided | VALIDATION_EXPERIMENT §5 |
| Accuracy auditor | An **independent volunteer**, recruited by the founder; not assumed to be available every day | VALIDATION_EXPERIMENT §6, EDITORIAL_PIPELINE §9.5 |
| News cutoff / publish target | **17:00 IST / 20:00 IST** | WORKFLOWS §4, ADR-017 |
| Editorial audit trail | **Mandatory for every edition** (14 items) | EDITORIAL_PIPELINE §14 |
| PD-01 to PD-07 | Approved at sign-off (§7) | All documents |
| Voice generation (2026-11-08) | **Self-hosted open-source TTS by default**: Kokoro primary, Piper `en_GB-cori-medium` alternative, provisional until the P1-05 benchmark; paid API optional; ₹0 expected voice spend with the $10 contingency cap kept | ADR-004, STRATEGY §6 |

## 1. What changed from the proposal

| Proposal item | Outcome |
|---|---|
| Hybrid LLM with possible Opus for T5 in production | **Changed:** Opus is evaluation and testing only. Production use would need measured evidence **and** a new founder decision |
| Local tier kept partly as a founder preference | **Changed:** kept only if it passes four measured criteria (ADR-003) |
| Soft launch around Day 31 | **Changed:** approved sequence puts the experiment at Days 1–14 and the soft launch at Days 15–30, with a preparation window before Day 1 |
| Epoch rule, the 10-edition error trigger, exception-based review | **Approved**; counting rule approved at sign-off (PD-03: public editions only) |
| Panel Y/N questions | **Changed:** every rated item now uses the 1–5 scale; thresholds mapped without loosening |
| Paid auditor and panel vouchers as options | **Not needed / not approved** (volunteer auditor; unpaid panel) |
| 90-day cash ₹5,190 expected / ₹12,480 max; 349 h | **Recalculated and signed off:** **₹5,690 expected / ₹13,380 worst case** (including pre-Day-1 spend); **≈ 433 h** (reconciled in STRATEGY §6.5 and §6.11) |

## 2. Editorial workload (summary)

The full model is in [EDITORIAL_PIPELINE §13](EDITORIAL_PIPELINE.md#13-human-involvement-model).

- **Automation prepares:** collection, clustering, rules, score proposals, evidence fetching, claim proposals, checks, drafts, second-pass check, narration, render, preview, deploy after approval.
- **Humans approve:** shortlist confirmation, claim confirmation (all claims in full review), final approval, plus corrections, skip decisions and sources.
- **Three workloads:**
  1. **Initial manual validation:** about 150 min per edition, about 35 h over the 14 days.
  2. **Engineering and automation:** about 252 h through Day 90 (one-off).
  3. **Mature editorial:** a **target of about 20 h/month by months 5–6**, not yet measured.

## 3. LLM (summary)

Full detail, with verified prices, is in [ADR-003](TECHNICAL_DECISIONS.md#adr-003).
- **Production routing:** local Ollama for T1 tagging and T2 duplicates, with Haiku fallback on failure or invalid output; Haiku 5.5 for T4 ranking; Sonnet 5.5 for T5 claims, T6 script and T7 second-pass verification. **About $12.4/month at 5 a week** (≈ ₹1,090), using assumed token volumes.
- **Local tier:** saves less than about $0.4/month at Haiku prices, so it stays only for measured resilience and scale benefits, never for purity. If it fails any benchmark, it routes to Haiku by config.
- **API cost vs local cost:** local inference uses the existing Mac. There is no new hardware; electricity isn't modelled; maintenance is counted as founder time.

## 4. Open decisions: recommended defaults

Approved decisions are in §0. The open decisions that remain are **not needed before Day 90**:

| ID | Decision | Recommended default | Alternatives | Cost implication | Dependencies |
|---|---|---|---|---|---|
| OD-01 | Brand, handle, domain | Working title for the private experiment; settle before gate G4 | Register now (risk of renaming after a pivot) | ₹1,000–2,500/yr *(verify)* | P0-05 → P1-20, P1-15 |
| OD-02 | TTS engine | **Decided 2026-11-08: self-hosted**, Kokoro primary and Piper `en_GB-cori-medium` alternative, both **provisional until the P1-05 benchmark** (ADR-004) | Paid API (now an optional fallback only) | ₹0 expected; $10 contingency cap kept | P1-05 → P1-06 |
| OD-04 | Supabase Free → Pro | Free through Day 90 with own backups; Pro at the Phase 5 gate | Pro from Phase 2 (+₹4,400, breaks the ceiling); self-hosted Postgres | ₹0 in the window | P2-01, P2-14 |
| OD-05 | VPS | Hetzner entry plan *(verify)* | Other providers; n8n on the Mac (rejected: the scheduler stops whenever the Mac sleeps) | ₹900 in the window | P2-12 |
| OD-07 | Instagram Login vs Facebook Login | Instagram Login | Facebook Login | ₹0 | P6-01 (after Day 90) |
| OD-09 | Privacy / DPDP advice | Before email signup (Phase 7) | — | Unknown | P7-02 |
| OD-10 | Code hosting | Private repo on GitHub Free *(verify the Actions allowance)* | Local git only | ₹0 | P0-04 |
| OD-11 | Email provider | P7-01 evaluation | — | — | After Day 90 |

## 5. 90-day financial model (summary, signed off)

The full model and reconciliation checks are in [STRATEGY §6](IMPLEMENTATION_STRATEGY.md#6-cost-model). It covers the preparation window plus Days 1–90, and **pre-Day-1 spend is included** (PD-01).

| Category | Expected | Worst case (every approved cap hit) |
|---|---:|---:|
| One-time (domain; LLM bake-off before Day 1; the voice benchmark is local and free) | ₹1,950 | ₹3,820 |
| Recurring infrastructure (VPS from Day 31; others on free plans) | ₹900 | ₹1,200 |
| LLM API ($10 Days 1–30 · **$20 Days 31–60** · $35 Days 61–90) | ₹1,990 | ₹5,720 |
| Voice generation (local; $10 contingency cap per window, PD-07) | ₹0 | ₹2,640 |
| **Cash total** | **₹4,840** | **₹13,380** |
| Headroom under ₹15,000 | ₹10,160 | ₹1,620 |
| Optional spend | Only via spending rule 1 (projected max ≤ ₹15,000); frozen if actual spend > ₹10,000 before Day 60 | |
| **Founder time (not cash)** | **≈ 433 h** = 255 engineering + 136 editorial + 42 review/ops (89 h of it in preparation) | |
| **Imputed labour at ₹500/h** | **≈ ₹2,16,500** | |
| **Fully loaded total** | **≈ ₹2.21 lakh** | ≈ ₹2.30 lakh |

The project does **not** cost ₹4,840–13,380; that is only the cash part. Earlier estimates are replaced but kept on record: 349 h / ₹1.75 lakh (proposal), then 428 h / ₹2.14 lakh (finalisation), now **433 h / ₹2.17 lakh** (sign-off; +5 h for the readiness gate, rubric sign-off, budget tracker and voice-cap review).

## 6. Key assumptions

| Assumption | Value | Status |
|---|---|---|
| Planning FX | ₹88 = $1 | Business plan convention |
| Anthropic prices and Batch discount | V-01, V-02 | **Verified (official)** |
| Token volumes per edition | ADR-003 table | **Assumed until measured** (P1-09, first 10 automated editions) |
| Voice generation | Local engine on the existing Mac; ₹0 cash; electricity not modelled | ADR-004 (engine provisional until P1-05) |
| All other provider prices and limits | V-06 to V-22 | **Unverified** |
| Engineering effort | Toolkit 12 days; Phase 2 10; Phase 3 11; Phase 4 4; deploy jobs 4; fixes 1 (6 h days) | Estimate |
| Editorial minutes per edition | 150 (experiment) → 130 → 120 → about 90 (mixed manual and automated) | Model; measured from Day 1 |
| Public editions by Day 90 | About 55 if there is no pivot | Depends on gates |
| Automated editions by Day 90 | About 11–18 | Depends on G6 and G7 |
| Excluded from cash | Hardware, internet, electricity, taxes, founder labour | Stated |

## 7. Decisions approved at sign-off (2026-11-07)

| ID | Approved decision | Effect | Recorded in |
|---|---|---|---|
| **PD-01** | All pre-Day-1 expenditure (about ₹900 expected) counts inside the ₹15,000 first-90-day ceiling | The bake-offs (and the domain, if bought early) sit inside the ceiling | STRATEGY §6.1, §6.11 |
| **PD-02** | Interim **$20/month LLM cap for Days 31–60**; $35 kept for other approved periods (Days 61–90; $10 stays for Days 1–30), always under the ₹15,000 ceiling | Worst case ₹14,680 → **₹13,380** | ADR-003, STRATEGY §6.4 |
| **PD-03** | The first 30 manual editions count **public editions only**; private prototypes and experiment drafts don't count | Sets when the manual full-review period ends (FR-M) | EDITORIAL_PIPELINE §9.2, TASKS §D |
| **PD-04** | Whether to return to 7 editions a week is decided **at the Day-90 review**; no cadence change before then | 5 a week until G9 | ADR-017, TASKS §C |
| **PD-05** | The final-five-day threshold is **median ≤ 130 minutes** | H3 definition fixed | VALIDATION_EXPERIMENT §3 |
| **PD-06** | Monday may include important Saturday and Sunday developments, scored on event date, publication date, freshness, significance and relevance; event and publication dates clearly separated; no penalty for weekend stories just because they were published earlier | **Rubric v1.1**: freshness measured against the edition window | EDITORIAL_PIPELINE §5.2, ADR-017 |
| **PD-07** | The **$10/month voice cap** stays until the vendor comparison is done; a $5 cap is reconsidered after measured usage | Worst case unchanged; review task P1-39 | ADR-003, STRATEGY §6.4 |

## 8. Contradictions found at finalisation and how they were handled

| # | Contradiction | Handling |
|---|---|---|
| 1 | The approved roadmap puts the experiment at Days 1–14, but it needs about 12 engineering days of tooling first | Added a **preparation window (Day −18 to 0)** with readiness gate G1; Days count from experiment Day 1; preparation cost and time are shown separately (PD-01) |
| 2 | Days 31–60 cannot hold all the requested automation (about 29 engineering days plus stability windows) | Kept the approved order; Phase 2 starts in Days 15–30; narration, render and deploy automation expected in Days 61–75; **gates, not dates**; logged as R24 |
| 3 | The first 30 automated editions can't all happen in Days 61–90 at 5 a week | Documented: about 11–18 by Day 90; full review continues beyond; G9 states that its evidence is partial |
| 4 | The approved $35 cap during Phase 3 development leaves ₹320 headroom in the worst case | **Resolved:** PD-02 approved ($20 for Days 31–60), giving ₹1,620 headroom. Note: giving Days 1–30 $35 as well would reach ₹15,580 (> ceiling), so $10 is kept |
| 5 | Gates written as "10 consecutive days" vs a 5-a-week cadence | Editorial gates are measured in consecutive editions (stricter in calendar time); ingestion stays in days |
| 6 | Yes/No panel items vs the required 1–5 scale | Mapped to "share rating ≥ 4" with the same percentages |
| 7 | The approved must-pass says "zero unresolved material errors", while v1 also capped total errors at ≤ 1 | Both kept: 0 unresolved is the must-pass; total ≥ 2 still triggers stop rule 1; corrected errors stay in the append-only log (**not loosened**) |
| 8 | "Final five days ≤ 130 min": median or every day? | **Resolved:** median ≤ 130 (PD-05 approved) |
| 9 | Opus appeared as a possible production tier in the proposal | Removed from production routing (approved: evaluation only) |
| 10 | The old "349 h / ₹1.75 lakh" estimate vs the new timeline | Recalculated to about 428 h / ₹2.14 lakh with a line-by-line reconciliation; the old figure is shown as replaced, not deleted |
| 11 | Instagram media ID is unavailable for manual uploads, but the audit trail requires a publication ID | Manual uploads record the permalink and shortcode plus a timestamp; the API media ID is recorded from Phase 6 |
| 12 | WF-02 and WF-06 were written for daily runs | Publishing workflows run on `PUBLISH_DAYS = Mon–Fri`; ingestion stays daily |

## 9. Documents changed

| Round | Documents |
|---|---|
| Proposal | VALIDATION_EXPERIMENT (new), DECISION_REVIEW (new), EDITORIAL_PIPELINE, TECHNICAL_DECISIONS, IMPLEMENTATION_STRATEGY, IMPLEMENTATION_ROADMAP, SYSTEM_ARCHITECTURE, DATABASE_DESIGN, WORKFLOWS, RISKS_AND_OPERATIONS, TASKS, CLAUDE.md |
| Finalisation | VALIDATION_EXPERIMENT (rewritten: preparation and G1, clarified thresholds, recruitment kit, auditor, error log); DECISION_REVIEW (this document); EDITORIAL_PIPELINE (§9 rewritten, §10 escalation and error log, **new §14 audit trail**); TECHNICAL_DECISIONS (ADR-003 approved and rewritten, ADR-017 approved, conflict register rows 2 and 9–18); IMPLEMENTATION_STRATEGY (§1, §5, §6 rewritten, §8, §9); IMPLEMENTATION_ROADMAP (**approved 90-day plan**, gate wording); RISKS_AND_OPERATIONS (§2 verification table with statuses, §4 caps, R22–R24); TASKS (restructured); DATABASE_DESIGN (edition JSON audit-trail fields); SYSTEM_ARCHITECTURE (Opus evaluation-only, `PUBLISH_DAYS`); WORKFLOWS (`PUBLISH_DAYS`); CLAUDE.md (approved decisions) |
| **Sign-off** | DECISION_REVIEW (§0, §1, §5, §7, §8, new §10); IMPLEMENTATION_STRATEGY (§6 signed-off cost model with §6.11 checks; §8, §9); TECHNICAL_DECISIONS (ADR-003 caps per budget period; ADR-017 PD-04 and PD-06; conflict rows 9, 10, 15, 18 and new 19–21); EDITORIAL_PIPELINE (rubric v1.1 §5.2; PD-03 counting rule); VALIDATION_EXPERIMENT (§2 points to the G1 checklist; PD-05, PD-06 clarifications); **new `docs/gates/G1_DAY1_READINESS.md`**; IMPLEMENTATION_ROADMAP; RISKS_AND_OPERATIONS (§4 caps); SYSTEM_ARCHITECTURE (`BUDGET_PERIODS_FILE`); CLAUDE.md; TASKS (user actions with due phases; PD statuses; new P1-36 to P1-39) |

## 10. Final planning sign-off (2026-11-07)

| Item | Status |
|---|---|
| All founder decisions (§0) and PD-01 to PD-07 (§7) | **Approved and recorded** in every relevant document |
| 90-day cash | **₹4,840 expected (₹5,690 before voice moved to local engines on 2026-11-08) / ₹13,380 worst case**, within ₹15,000 (₹1,620 worst-case headroom); no forecast reduction needed |
| Founder time | **≈ 433 h ≈ ₹2,16,500** at ₹500/h, reported separately from cash |
| Day-1 gate | [G1 checklist](gates/G1_DAY1_READINESS.md): 18 mandatory items, 6 optional |
| External verification | V-01 to V-05 verified on official pages; V-06 to V-22 still unverified ([TASKS §F](../TASKS.md#f-verification-tracker)) |
| Implementation | **Not started.** The preparation window begins only after the founder's explicit approval |

