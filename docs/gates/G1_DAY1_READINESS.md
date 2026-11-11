# G1 — Day-1 Readiness Checklist

**Purpose:** confirm that the 14-day validation experiment can start, and that its results will be valid. **Every mandatory item must pass. There is no partial start.** If any mandatory item fails, Day 1 moves; thresholds and format never change to make the date.
**When:** end of the preparation window (Day 0). **Owner of the decision:** the founder. **Task:** P1-38.
Related: [VALIDATION_EXPERIMENT](../VALIDATION_EXPERIMENT.md) · [TASKS §A](../../TASKS.md#a-user-actions) · [EDITORIAL_PIPELINE §5, §14](../EDITORIAL_PIPELINE.md)

## Mandatory (all must pass)

| # | Requirement | Pass criterion: how to check | Evidence | Owner | Tasks | ☐ |
|---|---|---|---|---|---|---|
| M1 | **Approved source list** | About 20 sources, each with a tier, category, working feed or page URL, and terms/robots note; approved by the founder | `sources.yaml`, `docs/EDITORIAL_CHARTER.md` | User | P1-01 | ☐ |
| M2 | **Two comparison AI-news roundups** | Two named roundups recorded as discovery-only references for H5 | Entry in `docs/gates/phase-1.md` | User | P1-01 | ☐ |
| M3 | **Reader panel: 8–12 confirmed** | ≥ 8 people have said yes, received the onboarding message and have a panel code. The code-to-name mapping is kept outside the repo | Roster of codes; onboarding sent | User | P1-18, P1-22 | ☐ |
| M4 | **Feedback form tested** | Daily form (D1–D6) and Day 7/14 form (W1–W4) on the 1–5 scale; one test response reached the sheet and exported to `experiment/panel-responses.csv` | Test row in the CSV | User | P1-21 | ☐ |
| M5 | **Independent accuracy auditor briefed** | The auditor has the responsibilities, audit record, escalation channel and availability calendar, and is not involved in scriptwriting | Calendar noted; channel agreed | User | P1-23 | ☐ |
| M6 | **One practice audit completed** | The auditor checked one fixture edition and filled at least one `audit-log.csv` row; one test escalation was sent and received | Audit-log row + escalation record | User + auditor | P1-24 | ☐ |
| M7 | **Editorial scoring rubric finalised** | Rubric **v1.1** (including the edition-window freshness rule, PD-06), hard rules R01–R12 and the eligibility threshold of 55 are frozen and signed. No changes during the experiment | Sign-off in `docs/gates/phase-1.md` | User | P1-37 | ☐ |
| M8 | **Evidence and claim records working** | `brief validate` **blocks** a material claim without evidence, an evidence URL that wasn't fetched, and an edition missing any audit-trail field (C01, C03) | Test run output | Eng | P1-02, P1-03 | ☐ |
| M9 | **Daily issue template ready** | `editions/_template.json` (all audit-trail fields) and the issue-page template render a fixture edition | Template file + rendered fixture page | Eng | P1-02, P1-11 | ☐ |
| M10 | **Script and caption workflow ready** | The script template (hook, segments, outro) is in the edition record; `brief caption` produces the caption from the **same** record; both pass C09 and C10 | Fixture caption output | Eng | P1-13 (caption part) | ☐ |
| M11 | **Narration and rendering tested** | Local TTS engine confirmed by the P1-05 benchmark (machine criteria and the commercial-licence gate in ADR-004; the listening test was waived by the founder on 2026-11-11, and voice C = Kokoro `am_adam` is set in `config/tts.yaml`); the pronunciation lexicon exists; **3 consecutive fixture renders** pass validation (1080×1920, 30 fps, H.264/AAC, 35–90 s, A/V difference < 100 ms, −14 ± 1 LUFS); one render of **real** content watched in full | ffprobe reports; bake-off report | Eng + user | P1-05, P1-06, P1-08, P1-10 | ☐ |
| M12 | **Source links validated** | `brief linkcheck` runs on a real dry-run edition, and every link returns 200 or is fixed | Linkcheck output | Eng | P1-04 | ☐ |
| M13 | **Issue page deployed** | Preview and production deploys work on `*.pages.dev` with `noindex`; `/today` resolves to the latest issue | Two URLs | Eng + user | P1-11, P1-12, P1-12U | ☐ |
| M14 | **Error log operational** | `experiment/error-log.csv` exists, append-only; `brief report experiment` refuses edited or deleted rows (test) | Test output | Eng | P1-19 | ☐ |
| M15 | **Experiment tracking sheet ready** | Templates for panel responses, audit log and coverage misses, plus `daily-notes.md`; `brief report experiment` dry run computes every §3 metric from fixture data | Dry-run report | Eng | P1-19, P1-14 | ☐ |
| M16 | **Daily time blocks scheduled** | 16:00–18:45 IST on 14 evenings, 15 min each morning, and the Day 7 checkpoint are in the calendar | Calendar | User | P1-31 | ☐ |
| M17 | **Pre-registered thresholds signed** *(added: required by the approved plan)* | VALIDATION_EXPERIMENT §3, including PD-05 (median of the final five editions ≤ 130 min), copied unchanged into `docs/gates/phase-1.md`, signed and dated | Signed section | User + eng | P1-25 | ☐ |
| M18 | **Spend limits and budget tracker in place** *(added: required to enforce the ₹15,000 ceiling from Day 1)* | Every paid account in use has a vendor spend limit (no voice account is needed unless the paid fallback is approved); `config/budget_periods.yaml` caps are LLM $10 and voice $10 for Days 1–30; `brief cost report` shows actual spend plus the projected max against ₹15,000, including preparation spend | Cost report output | User + eng | P1-26, P1-27, P1-36 | ☐ |

## Optional improvements (they do not block Day 1)

| # | Improvement | Why it helps |
|---|---|---|
| O1 | The panel reaches 10–12 people with the full target mix (developers, students and professionals, founders; ≥ 2 outside India) | Richer, less biased feedback |
| O2 | The auditor is available for pre-publication spot checks on at least 3 days a week, or a backup volunteer is found | More errors caught before distribution; higher audit coverage |
| O3 | One timed **dress-rehearsal edition**, run end to end and not counted | Finds workflow friction before Day 1 |
| O4 | LLM-assisted drafting ready (P1-13). If used, it must be used **on all days or none** | Faster scripts. Optional by design |
| O5 | The pronunciation lexicon covers all 20 benchmark test terms | Fewer narration fixes |
| O6 | The two reference roundups' recent issues are saved for comparison | Makes coverage-miss checks faster |

## Sign-off

| Field | Value |
|---|---|
| Date checked | |
| Mandatory items passed | __ / 18 |
| Decision | ☐ **Pass**: start Day 1 on ____ · ☐ **Fail**: move Day 1; failing items and owners: ____ |
| Signed (founder) | |

When this checklist passes, gate **G1** is marked passed in [TASKS §C](../../TASKS.md#c-decision-gates-and-milestones).
