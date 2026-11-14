# Phase 1 gate record — validation experiment

Gate records for Phase 1 ([IMPLEMENTATION_ROADMAP](../IMPLEMENTATION_ROADMAP.md)): what was frozen before Day 1, the Day 7 checkpoint (G2) and the Day 14 decision (G3). Sections 1–3 are filled **before Day 1** and never edited afterwards. Later sections are appended as the experiment runs.

## 1. Pre-registered thresholds (P1-25, G1 M17)

Copied **unchanged** from [VALIDATION_EXPERIMENT §3](../VALIDATION_EXPERIMENT.md#3-hypotheses-metrics-and-thresholds-pre-registered). `tests/test_gate_records.py` fails if the text between the markers ever differs from §3. The Day 7 checkpoint may change the format, never these thresholds.

<!-- BEGIN PRE-REGISTERED §3 (do not edit) -->
| # | Hypothesis | Metric (source) | Threshold | Class |
|---|---|---|---|---|
| C | **Completion** | Complete editions: validated, rendered, page deployed, reviewed | ≥ 10 of 14 days | **Must-pass** |
| H2 | **Accuracy and provenance** | (a) % of material claims with supporting evidence records; (b) **unresolved** material or critical errors at Day 14; (c) total material or critical errors, **corrected or not**, from the append-only [error log](#9-data-captured) | (a) 100%; (b) **0**; (c) ≤ 1. Two or more triggers stop rule 1 even if all were corrected | **Must-pass** (a, b); (c) feeds the stop rule |
| H4 | **Usefulness** (early qualitative signal) | Daily item D1 "Today's brief was useful to me" (1–5); response rate | Mean of all D1 responses **≥ 3.8**, with panel response rate ≥ 50% of panel-days (otherwise the measure is **invalid**, not passed) | **Must-pass** |
| H6 | **Production stability** | Renders needing no manual FFmpeg or template fix; deploy success | ≥ 13/14 renders (≥ 90%); the last 5 renders pass validation first time; 100% of deploys succeed | **Must-pass** |
| H1 | **Supply** | Eligible stories per day: rules pass, score ≥ 55, evidence present | ≥ 5 eligible on ≥ 10 of 14 days, **and** ≥ 3 on every day | Should-pass |
| H3 | **Time** | Edition minutes (`production_log`; audit and panel overhead excluded) | Median ≤ 150 over all editions **and** median of the final 5 editions ≤ 130 | Should-pass |
| H5 | **Distinctiveness and coverage** | (a) W1 "meaningfully different from the AI-news sources I already use" on Days 7 and 14; (b) major-story misses vs the two reference roundups (discovery-only) | (a) ≥ 50% of respondents rate ≥ 4; (b) ≤ 2 misses of stories that met our rules | Should-pass |

**Diagnostics** (reported, not pass/fail): D2 clarity and pacing, D3 trust, D4 story selection, D5 "learned something new" (the v1 threshold of "≥ 60% say yes" is now measured as **≥ 60% of responses rating ≥ 4**), W2 likelihood of watching regularly, W3 likelihood of visiting the website. The derived post-automation time projection uses [EDITORIAL_PIPELINE §13](EDITORIAL_PIPELINE.md#13-human-involvement-model).

**Clarifications recorded at finalisation** (none of them loosens a threshold):
1. "Zero unresolved material errors" is the must-pass test. A corrected error **stays in the error log and still counts** toward H2(c) and stop rule 1. It is never erased or treated as if it didn't happen.
2. H3 "at most 130 minutes over the final five days" is the **median of the final five editions ≤ 130 minutes** (PD-05, **approved** 2026-11-07).
3. Questionnaire items moved from Yes/No to the 1–5 scale. The mappings are: "learned something new ≥ 60% Yes" becomes "≥ 60% rate D5 ≥ 4", and "would follow ≥ 50% / < 30%" becomes "W2 ≥ 4 for ≥ 50% / < 30%".
4. Rubric v1.1 (PD-06) is used. With a daily cadence its scores are identical to v1.0, so H1 is unaffected; the eligibility threshold of 55 is fixed for the experiment.
<!-- END PRE-REGISTERED §3 -->

| Sign-off | Founder | Date |
|---|---|---|
| I have read the thresholds above, they are unchanged from §3, and they are fixed for the experiment | | |

## 2. Rubric v1.1 freeze (P1-37, G1 M7)

Frozen for the 14-day experiment ([EDITORIAL_PIPELINE §5–§6](../EDITORIAL_PIPELINE.md#5-ranking--the-100-point-rubric-briefintelscorepy-score_version--11)):
- **Rubric v1.1** (`score_version = "1.1"`), 100 points: significance 25, source confidence 25, freshness 20, practical relevance 15, novelty 10, audience fit 5.
- **Freshness** is scored against the **edition window** using `event_at`, not `published_at` (PD-06). With the daily cadence of the experiment, v1.1 scores are identical to v1.0.
- **Hard rules R01–R12** are applied before scoring and override any score.
- **Eligibility threshold: 55.** It does not change during the experiment (H1 depends on it).

Fingerprint of EDITORIAL_PIPELINE §5 and §6 (from `## 5. Ranking` up to `## 7. Claims`) at the time of this record:
`sha256 6fb72ca402e9cfce5935ea948d17a719da40e204ca670bb186c0f1202c7c9a6c`

`tests/test_gate_records.py` fails if those sections change. Any change before Day 1 needs a new sign-off and a new fingerprint. During the experiment, no change is allowed.

| Sign-off | Founder | Date |
|---|---|---|
| Rubric v1.1, hard rules R01–R12 and the threshold of 55 are frozen for the experiment | | |

## 3. Reference roundups for H5 (P1-01, G1 M2)

Two existing AI-news roundups used **only** as discovery-only references for H5(b), counting major-story misses. They are never evidence for a claim.

| # | Roundup | URL | Cadence | Chosen by | Date |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |

## 4. Day 7 checkpoint (G2, P1-32)

*Appended on Day 7: metrics so far (`uv run brief report experiment`), format changes decided (if any). Thresholds in §1 stay unchanged.*

## 5. Results and decision (G3, P1-17)

*Appended on Day 14–15: every §1 metric with its measured value, the error log status, and the decision (continue / pivot / stop) with reasons, following [VALIDATION_EXPERIMENT §8](../VALIDATION_EXPERIMENT.md#8-decision-rules-at-day-14-p1-17).*
