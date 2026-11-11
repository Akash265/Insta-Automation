# P1-40 blind listening test (TTS benchmark)

> **Waived 2026-11-11 (founder decision).** Voice C (Kokoro `am_adam`) was chosen without listener ratings. These materials are kept in case a test is ever run; note the key has now been opened.

**Who:** at least 3 independent listeners (reader-panel volunteers are fine), codes L1, L2, L3…
The founder may also score, using code **F**. That sheet is included in the results but does not count toward the 3.
**Time:** about 15 minutes per listener.
**Rule:** listeners must not see `KEY-do-not-open-until-scored.json` or any engine name.
The founder should score **before** opening the key.

## What to send each listener
- The clips in `clips/` (they are local files, not in git: share them privately).
- This page's "How to score" section, and their own copy of `scoring-sheet.csv`.
- A listener code (L1, L2, L3…). No names in the repo.

## How to score
Each voice has two clips with the same letter:
- `X-main.wav`: the 5-story news script (about 75 s).
- `X-names.wav`: a passage containing 20 AI names.

Listen in any order, with headphones if possible. For **each clip letter**, fill one row:

| Column | What to enter |
|---|---|
| `naturalness_1to5` | 1 = Strongly disagree … 5 = Strongly agree with: *"This sounds like a natural, pleasant news narrator I'd listen to daily."* Rate the **main** clip |
| `mispronounced_terms` | From the **names** clip: every one of the 20 names that sounded wrong, separated by `;` |
| `other_mispronounced_words` | Any ordinary word or number in either clip that sounded wrong |
| `artefacts` | `none`, `minor` or `major`: glitches, cut-offs, robotic warble, odd breaths, clicks |
| `artefact_notes` | Where it happened (clip and roughly when) |
| `comments` | Anything else (pace, tone, clarity) |

The 20 names: OpenAI, Anthropic, Claude, Gemini, DeepMind, Llama, Mistral, Qwen, DeepSeek,
Hugging Face, PyTorch, NVIDIA, CUDA, arXiv, GPT-4o, Ollama, vLLM, LangChain, Perplexity, Kokoro.

## How results are used (ADR-004 acceptance criteria)
- **Naturalness:** mean ≥ 3.5 across listeners, and no listener below 3.
- **Pronunciation:** ≥ 16/20 names correct out of the box. All 20 must be fixable with lexicon entries, and no ordinary word may be mispronounced. A name counts as wrong if **≥ 2 listeners** flag it.
- **Audio quality:** no artefact flagged `minor` or `major` by ≥ 2 listeners.

The founder collects the sheets into `results/listening-scores.csv` (codes only). **These
scores are never filled in by the engineer or a tool.**

## Analysing the results
From `research/tts-benchmark/`:

```
python3 analyse_listening.py            # still blind: verdicts by clip letter
python3 analyse_listening.py --reveal   # then: map letters to engines
```

The script refuses an incomplete sheet: fewer than 3 independent listeners, a missing clip,
a score outside 1–5, an unknown name or an unknown artefact value. It reads the key only
with `--reveal`, and first checks that the clips still match the hashes in the key. It
writes `results/listening-analysis.md`. Copy the verdicts into `results.md` and ADR-004.
