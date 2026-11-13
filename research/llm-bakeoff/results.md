# P1-09 LLM bake-off: results

**Status:** machine measurements complete (2026-11-13). **The editor ratings are still to come**: claim precision, claim-type accuracy, script quality and the review of the checker's flags. Until then the routes below are provisional, and so is the ADR-003 Opus question.

- **Spend:** $2.13 of the $7 preparation cap, all logged in `finance/usage-ledger.jsonl`.
- **Daily cap:** raised to $3.00 for the preparation period only (founder approval, 2026-11-13).
- **Reproduce:** `uv run python research/llm-bakeoff/bakeoff.py fetch|run …`, then `score.py`. Raw outputs are in `runs/`, and the numbers below are in `results/scores.json`.

## Setup

- **Stories:** 10 real primary-source stories dated 16 Oct – 12 Nov 2026, approved by the founder (`stories.yaml`). There are two per category, and six carry company benchmark numbers. The full text was fetched on 2026-11-13 with the safe fetcher; hashes are in `sources-manifest.json` and the text itself is in the git-ignored `cache/`.
- **Feed items:** 100 real items from six feeds (arXiv cs.CL, the Hugging Face blog, Ollama releases, HN front page, The Verge, Google AI blog), deliberately mixing AI and non-AI items.
- **Pairs:** 40 item pairs for the same-event test: the 30 most similar titles across feeds plus 10 random pairs.
- **Effort:** each model runs at its own default, which is how production would call it: Haiku medium, Sonnet high, Opus medium. For tagging and same-event, Haiku runs at low. Sonnet at medium was also recorded for claim extraction.
- **Output:** structured JSON, checked again on our side.
- **Prompts:**
  - `claims.v2`. In v1, "up to 10" plus "precision over coverage" led Sonnet to return a single claim on 4 of 10 stories; those runs are kept in `runs/T5-claims.v1-superseded`.
  - `script.v2`. v1 never asked for the benchmark caveat, and both models failed check C07 5–6 times; those runs are kept in `runs/T6-script.v1`.
  - `critic.v1`, `tag.v1`, `same_event.v1`.

## T5: claim extraction (10 stories)

| Model (effort) | Claims (per story) | URL = given source | Excerpt verbatim | Cost, 10 stories | Mean tokens in / out | p50 |
|---|---|---|---|---:|---|---:|
| Haiku 5.5 (medium) | 86 (4–10) | 100% | 99% (85/86; 100% ignoring quote and dash styles) | $0.017 | 5,758 / 2,244 | 7.9 s |
| Sonnet 5.5 (medium) | 76 (**1 on two stories**) | 100% | 100% | $0.248 | 5,758 / 1,332 | 8.9 s |
| Sonnet 5.5 (high) | 88 (**1 on the Fable/Mythos 5.2 page**) | 100% | 100% | $0.275 | 5,758 / 1,598 | 9.5 s |
| Opus 5.5 (medium, evaluation only) | 98 (9–10 on every story) | 100% | 100% | $0.575 | 5,758 / 1,722 | 13.3 s |

- **The hard rules held for every model:** no invented URLs and no paraphrased "quotes". Both are checked automatically in production (C03, and the excerpt check in P3-06).
- **Sonnet under-extracted.** On the Anthropic "Claude Fable 5.2 and Claude Mythos 5.2" page, Sonnet returned one claim in all three runs (v1 medium, v2 medium, v2 high), while Haiku and Opus returned 10. There was no refusal (`end_turn`). This is a real risk for the production route: a story could reach review with almost no claims. A pipeline check should flag a story whose claim count is far below its source length (proposed for P3-06).
- **Pending, from the editor's sheet:** claim precision (is each claim supported by its excerpt?), claim-type accuracy and "would use". These decide the ADR-003 Opus rule: propose Opus only if its claim precision is ≥ 10 points higher than Sonnet's, or it has ≥ 50% fewer unsupported claims.

## T6: script (two 5-story editions, `script.v2`, same rule-checked claims for all)

| Model | Blocking issues | Warnings / limits | Narration words (E1, E2; target 160–230) | Cost, 2 editions | Mean tokens in / out |
|---|---|---|---|---:|---|
| Haiku 5.5 | 0 | 1 (a 5-sentence summary) | 204, 200 | $0.008 | 4,340 / 7,023 |
| Sonnet 5.5 (high) | 1, a **false alarm** (a date) | 1 + one narration of 41 words | 220, 212 | $0.154 | 4,340 / 6,820 |
| Opus 5.5 | 5, all **false alarms** (4 dates, 1 "10" vs "ten") | 1 | 208, 203 | $0.218 | 4,340 / 4,572 |

- **Check C04 has a false positive.** It blocks day numbers in dates ("announced on November 9") and digits written as words in the claims ("ten"). Every blocking issue in the v2 runs is one of these. **Fix proposed:** accept numbers that match the story's own dates, and number words. That's a small change to `brief/edition/checks.py`, for the founder to approve; it isn't made yet.
- **`script.v2` fixed every attribution and benchmark-caveat failure** (C07) that v1 produced.
- **Pending, from the editor's sheet:** accuracy, clarity and "would publish" for each script, blind.

## T7: second-pass critic (Sonnet's v1 scripts, clean and with 5 planted errors per edition)

| Model | Planted errors found | Flags on the clean scripts (to review) | Cost, 4 calls |
|---|---|---|---:|
| Haiku 5.5 | 7/7 | 6 | $0.007 |
| Sonnet 5.5 (high) | 7/7 | 4 | $0.100 |
| Opus 5.5 | 7/7 | 3 | $0.147 |

- **Coverage:** the planted errors covered a changed number, a swapped company name, an added superlative, a wrong "today" and an unsupported added sentence. Only 7 could be planted, because the first two scripts didn't contain every pattern.
- **The flags on the clean scripts look mostly real:** a missing attribution on a card, a dropped "with four DataLoader workers" condition, and "Claude Fable 5.2" where the claims gave the version only for Mythos. The editor confirms these in `ratings/T7-clean-flags-review.csv`.

## T1 and T2: local tier vs Haiku (ADR-003 retention criteria)

| Model | T1 in-scope agreement | T1 category agreement | T2 same-event agreement | Invalid or failed | p50 / p95 per item | Batch time | Memory when loaded |
|---|---|---|---|---|---|---|---|
| Haiku 5.5 (reference, low effort) | — | — | — | 0% | T1 1.3 / 1.9 s · T2 1.5 / 2.4 s | 100 items in 145 s | — |
| qwen2.5:7b | **89%** | 67% | 98% | 0% | T1 2.7 / 4.6 s · T2 4.4 / **5.3 s** | 100 items in 303 s | 4.8 GB |
| gemma4:e4b | **89%** | 74% | 92% | 0% after stripping fences (27% / 75% before) | T1 1.2 / 2.4 s · T2 2.3 / **5.1 s** | 100 items in 138 s | 9.4–12 GB |

- **Quality fails for both local models** (the threshold is ≥ 95% agreement with Haiku): in-scope agreement is 89%, and category agreement 67–74%. Same-event F1 against a labelled set waits for P2-08. qwen's 98% raw agreement is encouraging.
- **Latency:**
  - The cut-off batch (about 120 items) fits in 10 minutes for both models.
  - T2's p95 is just over 5 s for both. T1's p95 passes.
  - Cold loads take 3–28 s.
- **Reliability and format:**
  - qwen produced valid schema output every time.
  - **`gemma4:e4b` has no structured output in Ollama 0.40.16.** It runs on the MLX runner, which reports "structured output is unavailable". It needed the JSON schema in the prompt and fence stripping before its output was valid.
- **Memory (V-07):**
  - While a model was loaded, swap stayed near full (about 12 of 13 GB with qwen, about 15 of 16 GB with gemma), with other apps open.
  - That makes the local tier a real contention risk next to the FFmpeg render on a 16 GB Mac (risk R20).
  - **Unloading works (V-06):** `keep_alive: 0` removed both models, as confirmed by `/api/ps`.
- **Cost:** Haiku costs $0.0082 per 100 T1 items and $0.004 per 40 T2 pairs. At 120 items and 20 pairs per edition that's about **$0.012 per edition, or about $0.26/month**.
- **Recommendation:** route **T1 and T2 to Haiku** now, through config with no code change, as ADR-003 provides for. Re-test the local tier in P2-17 on the labelled set, with qwen2.5:7b as the candidate. Drop gemma4:e4b on memory and format grounds.

## Measured token volumes vs ADR-003 assumptions

| Task | ADR-003 assumption (in / out) | Measured, production model (in / out; output includes thinking) |
|---|---|---|
| T5 per story | 8k / 1.2k | 5.8k / 1.6k (Sonnet, high) |
| T6 per edition | 15k / 4k | 4.3k / 6.8k (Sonnet, high) |
| T7 per edition | 12k / 1.5k | 5.5k / 1.4k (Sonnet, high) |
| T1 per item | 0.8k / 0.1k | 0.63k / 0.04k (Haiku, low) |
| T2 per pair | 0.6k / — | 0.6k / 0.08k (Haiku, low) |

## Cost per edition (measured mean cost per call × ADR-003 volumes: 10 claim extractions + 1 script + 1 critic, +20% assumed repairs)

| Model for T5–T7 | Per edition | 22 editions/month | vs Days 1–30 cap ($10) |
|---|---:|---:|---|
| Haiku 5.5 | $0.03 | $0.60 | 6% |
| **Sonnet 5.5 (high)** | **$0.45** | **$9.95** | **99%: drafting every day uses almost the whole cap** |
| Opus 5.5 | $0.87 | $19.0 | over the cap (and evaluation-only) |

Plus T1/T2 on Haiku: about $0.26/month. The ADR-003 estimate was about $12.4/month at 5 editions a week, so the measured Sonnet cost is close to it. During Days 1–30, the optional LLM draft (P1-13) on Sonnet would leave almost no headroom under the $10 cap.

## Provisional routes (`config/llm_routes.yaml` v1 after the ratings)

| Task | Proposed | Why |
|---|---|---|
| T1 tagging, T2 same-event | **Haiku 5.5** (low) | The local tier fails the quality criterion; Haiku is about $0.26/month |
| T4 triage | Haiku 5.5 | As in ADR-003 (not tested here) |
| T5 claims | Sonnet 5.5 (high), pending ratings | Rules 100%, but it under-extracts on 1 of 10 stories. Opus is more complete; the ADR rule decides on precision |
| T6 script | Sonnet 5.5 (high) with `script.v2`, pending ratings | Haiku also passes the checks at a twentieth of the cost; the editor's quality ratings decide |
| T7 critic | Sonnet 5.5 (high) | All models caught 7/7 planted errors; Haiku is a cheap option under the budget ladder |

## For the editor: how to rate (about 45 minutes)

1. Open `ratings/T5-claims-sheet.csv`. It has 272 claims from three models, shown as letters A, B and C, shuffled per story. For each row, fill:
   - `editor_supported_y_n`: is the claim fully supported by its excerpt?
   - `editor_type_correct_y_n`
   - `editor_would_use_y_n`

   To save time, rate at least 5 stories in full; every claim in a rated story must be rated.
2. Open `ratings/T6-scripts-sheet.csv`. It has 6 scripts. Fill accuracy (1–5), clarity (1–5) and would-publish (y/n).
3. Open `ratings/T7-clean-flags-review.csv`. It has 13 flags. Fill `editor_real_issue_y_n`.
4. Don't open the `KEY-*` files. Run `uv run python research/llm-bakeoff/score.py --ratings`, which unblinds the sheets and computes the scores.
