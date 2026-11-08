# P1-05 local TTS benchmark: results (run 1, 2026-11-08)

**Status: machine measurements complete. Human listening (P1-40) pending. No engine is enabled for production.**
Paid TTS fallback: disabled. Voice spend: ₹0 (no paid API used); contingency caps unchanged.

## Setup
- **Hardware:** Apple M5, 16 GB unified memory, macOS 26.6.2, Python 3.12.16. Each candidate ran in its own process.
- **Packages** (isolated environment `research/tts-benchmark/`, locked in its `uv.lock`, with the same 14-day age guard): kokoro 0.9.4, misaki 0.9.4, torch 2.14.1, piper-tts 1.8.0, onnxruntime 1.31.0, spacy 3.8.16 + en_core_web_sm 3.8.0, phonemizer-fork 3.3.2, espeakng-loader 0.2.4.
- **Models:** pinned to Hugging Face revisions `hexgrad/Kokoro-82M@f3ff3571791e` and `rhasspy/piper-voices@e7229f7d33a1`. SHA-256 for every file is in `results/model-manifest.json`; licence evidence is in `licences.md`.
- **Text:** `script.md` (main script 188 words; pronunciation passage with the 20 names in 11 natural sentences).
- **Offline:** generation used only local model files with the Hugging Face hub in offline mode. During the 20-run test, a socket guard refused any non-loopback connection.

## Machine measurements (full main script, median of 3 runs after warm-up)

| Candidate | Load + warm-up (s) | Generation (s) | Audio (s) | Real-time factor | Peak RSS (MB) | Sample rate (Hz) | Raw clipped samples | Raw true peak (dBTP) | After loudnorm: LUFS / dBTP | Offline runs | Repeat runs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| `kokoro-af_heart-cpu` | 11.31 | 14.861 | 82.08 | 0.18 | 2,402 | 24,000 | 0 | -5.6 | -14.8 / -1.0 | 20/20 | same length, bytes differ |
| `kokoro-am_adam-cpu` | 6.72 | 12.333 | 79.28 | 0.16 | 2,276 | 24,000 | 0 | -1.7 | -15.9 / -1.0 | 20/20 | same length, bytes differ |
| `kokoro-bf_emma-cpu` | 6.44 | 12.361 | 78.85 | 0.16 | 2,239 | 24,000 | 0 | -4.3 | -15.2 / -1.0 | 20/20 | same length, bytes differ |
| `kokoro-af_heart-mps` | 18.5 | 8.023 | 82.08 | 0.10 | 901 | 24,000 | 0 | -6.0 | -14.7 / -1.0 | 20/20 | same length, bytes differ |
| `piper-en_GB-cori-medium-cpu` | 1.72 | 2.812 | 71.89 | 0.04 | 469 | 22,050 | 16 | 0.1 | -14.8 / -1.0 | 20/20 | length varies by 2.56 s |

Notes:
- **Memory (MPS run):** RSS may not include memory the Apple GPU allocates through MPS, so the MPS figure is a lower bound.
- **Loudness:** single-pass `loudnorm` landed at −14.7 to −15.9 LUFS. The render step (P1-10) should use two-pass linear normalisation to hit −14 ± 1 LUFS. True peak was −1.0 dBTP for every candidate.
- **Piper output** touches full scale (16 samples at |x| ≥ 0.999, raw true peak +0.1 dBTP) before normalisation. Listeners should check for audible distortion.
- **Kokoro repeat runs** have identical durations but differ at the byte level (floating-point variation). Perceptual identity needs listening.
- **Piper repeat runs** vary in length by up to 2.6 s: prosody is randomised with default settings. Re-test with Piper's noise parameters fixed before treating it as repeatable.

## Acceptance criteria (ADR-004): machine-checkable part

| Criterion | Kokoro (af_heart, am_adam, bf_emma) | Piper (en_GB-cori-medium) |
|---|---|---|
| Commercial licensing (hard gate) | **Pass** (Apache-2.0 code and weights; permissive training data). Note: CC BY training audio, so attribution is recommended (`licences.md`) | **Not passed: unresolved.** Piper's "personal use and research only" statement (V-24) |
| Generation time ≤ 60 s for the full script; first load ≤ 60 s | **Pass** (CPU 12.3–14.9 s; MPS 8.0 s; load ≤ 18.5 s) | **Pass** (2.8 s; load 1.7 s) |
| Peak memory ≤ 4 GB; no CUDA | **Pass** (CPU ≈ 2.2–2.4 GB; CPU and MPS only) | **Pass** (≈ 0.5 GB; CPU only) |
| Sample rate ≥ 22.05 kHz mono; true peak ≤ −1 dBTP after normalising | **Pass** (24 kHz mono; −1.0 dBTP) | **Pass, but marginal** (exactly 22,050 Hz; −1.0 dBTP; raw output touches full scale) |
| 20 consecutive offline generations, 0 crashes | **Pass** (20/20 for every voice and device) | **Pass** (20/20) |
| Repeat runs identical or perceptually identical | **Likely**: same length, bytes differ (listening to confirm) | **Fails as configured** (length varies); re-test with fixed noise settings |
| Naturalness (blind mean ≥ 3.5, no listener < 3) | **Pending P1-40** | **Pending P1-40** |
| Pronunciation (≥ 16/20 out of the box; 20/20 with lexicon; 0 ordinary words wrong) | **Pending P1-40** | **Pending P1-40** |
| No audible artefacts flagged by ≥ 2 listeners | **Pending P1-40** | **Pending P1-40** |

**Provisional standing:** Kokoro passes every machine-checkable criterion and the licence gate, so it remains the
provisional primary. Piper stays provisional and **not selectable** until V-24 is resolved and its repeatability is
re-tested. **No final selection is made until the listening results exist.**

## Pronunciation evidence (phoneme readings, not verdicts)

These are the phonemes each engine produced for the 11 sentences containing the 20 names. They show what the engine
*intends* to say. Whether it *sounds* right is judged by listeners. One observation is objective: both engines read
**"Qwen" as /kjuːwɛn/ ("Q-wen")**, not "chwen", which suggests a lexicon entry will be needed. Listeners confirm.
`af_heart` and `am_adam` share Kokoro's US English G2P; `bf_emma` uses the British G2P.

| Sentence | Kokoro US (`af_heart`, `am_adam`) | Kokoro UK (`bf_emma`) | Piper (`en_GB-cori-medium`) |
|---|---|---|---|
| OpenAI and Anthropic both updated their developer guides this week. | `ˌOpᵊnˈAˌI ænd ænθɹˈɑpɪk bˈOθ ˈʌpdˌATᵻd ðɛɹ dəvˈɛləpəɹ ɡˈIdz ðɪs wˈik.` | `ˌQpᵊnˈAˌI and anθɹˈɒpɪk bˈQθ ˌʌpdˈAtɪd ðɛː dɪvˈɛləpə ɡˈIdz ðɪs wˈiːk.` | `ˈəʊpən ˌeɪˈaɪ and anθɹˈɒpɪk bˈəʊθ ʌpdˈeɪtɪd ðeə dɪvˈɛləpə ɡˈaɪdz ðɪs wˈiːk.` |
| Claude now appears next to Gemini in several comparison tables. | `klˈɔd nˈW əpˈɪɹz nˈɛkst tə ʤˈɛmənˌI ɪn sˈɛvəɹəl kəmpˈɛɹəsᵊn tˈAbᵊlz.` | `klˈɔːd nˈW əpˈɪəz nˈɛkst tə ʤˈɛmɪniː ɪn sˈɛvəɹəl kəmpˈaɹɪsᵊn tˈAbᵊlz.` | `klˈɔːd nˈaʊ ɐpˈiəz nˈɛkst tə dʒˈɛmɪnˌaɪ ɪn sˈɛvɹəl kəmpˈaɹɪsən tˈeɪbəlz.` |
| Researchers at Google DeepMind shared new evaluation notes. | `ɹəsˈɜɹʧəɹz æt ɡˈuɡᵊl dˌipmˈInd ʃˈɛɹd nˈu əvˌæljʊˈAʃən nˈOts.` | `ɹɪsˈɜːʧəz at ɡˈuːɡᵊl dˌiːpmˈInd ʃˈɛːd njˈuː ɪvˌaljʊˈAʃᵊn nˈQts.` | `ɹɪsˈɜːtʃəz at ɡˈuːɡəl dˈiːp mˈaɪnd ʃˈeəd njˈuː ɪvˌaljuːˈeɪʃən nˈəʊts.` |
| Teams testing Llama, Mistral and Qwen models posted their results. | `tˈimz tˈɛstɪŋ lˈɑmə, mˈɪstɹᵊl ænd kjˈuwˈɛn mˈɑdᵊlz pˈOstᵻd ðɛɹ ɹəzˈʌlts.` | `tˈiːmz tˈɛstɪŋ lˈɑːmə, mˈɪstɹᵊl and kjˈuːwˈɛn mˈɒdᵊlz pˈQstɪd ðɛː ɹɪzˈʌlts.` | `tˈiːmz tˈɛstɪŋ lˈɑːmə, mˈɪstɹəl and kjˈuːwˈɛn mˈɒdəlz pˈəʊstɪd ðeə ɹɪzˈʌlts.` |
| DeepSeek released new open weights on Hugging Face. | `dˌipsˈik ɹəlˈist nˈu ˈOpᵊn wˈAts ˌɔn hˈʌɡɪŋ fˈAs.` | `dˌiːpsˈiːk ɹɪlˈiːst njˈuː ˈQpᵊn wˈAts ˌɒn hˈʌɡɪŋ fˈAs.` | `dˈiːp sˈiːk ɹɪlˈiːst njˈuː ˈəʊpən wˈeɪts ˌɒn hˈʌɡɪŋ fˈeɪs.` |
| Early users run them with PyTorch on a single NVIDIA card using CUDA. | `ˈɜɹli jˈuzəɹz ɹˈʌn ðˌɛm wɪð pˈI tˈɔɹʧ ˌɔn ɐ sˈɪŋɡᵊl ɛnvˈɪdiə kˈɑɹd jˈuzɪŋ sˌijˌudˌiˈA.` | `ˈɜːli jˈuːzəz ɹˈʌn ðˌɛm wɪð pˈI tˈɔːʧ ˌɒn ɐ sˈɪŋɡᵊl ɛnvˈɪdɪə kˈɑːd jˈuːzɪŋ sˌiːjˌuːdˌiːˈA.` | `ˈɜːlɪ jˈuːzəz ɹˈʌn ðˌɛm wɪð pˈaɪ tˈɔːtʃ ˌɒn ɐ sˈɪŋɡəl ˈɛnvˈɪdiʲə kˈɑːd jˈuːzɪŋ kjˈuːdə.` |
| The full paper is available on arXiv. | `ðə fˈʊl pˈApəɹ ɪz əvˈAləbᵊl ˌɔn ˈɑɹkˌIv.` | `ðə fˈʊl pˈApə ɪz əvˈAləbᵊl ˌɒn ˈɑːkIv.` | `ðə fˈʊl pˈeɪpəɹ ɪz ɐvˈeɪləbəl ˌɒn ˈɑː zˈɪv.` |
| Several guides still use GPT-4o as their baseline. | `sˈɛvəɹəl ɡˈIdz stˈɪl jˈuz ʤˌipˌitˈi fˈɔɹ ˈO æz ðɛɹ bˈAslˌIn.` | `sˈɛvəɹəl ɡˈIdz stˈɪl jˈuːz ʤˌiːpˌiːtˈiː fˈɔː ˈQ az ðɛː bˈAslIn.` | `sˈɛvɹəl ɡˈaɪdz stˈɪl jˈuːz dʒˌiːpˌiːtˈiː  fˈɔːɹ ˈəʊ az ðeə bˈeɪslaɪn.` |
| Ollama makes local models easy to try, and vLLM speeds up serving. | `ɑlˈɑmə mˌAks lˈOkəl mˈɑdᵊlz ˈizi tə tɹˈI, ænd vˌiˌɛlˌɛlˈɛm spˈidz ˌʌp sˈɜɹvɪŋ.` | `ɒlˈɑːmə mˌAks lˈQkᵊl mˈɒdᵊlz ˈiːzi tə tɹˈI, and vˌiːˌɛlˌɛlˈɛm spˈiːdz ˌʌp sˈɜːvɪŋ.` | `ɒlˈɑːmə mˌeɪks lˈəʊkəl mˈɒdəlz ˈiːzi tə tɹˈaɪ, and vˈiːʲ ˌɛlˌɛlˈɛm spˈiːdz ˌʌp sˈɜːvɪŋ.` |
| LangChain helps connect models to your own data. | `lˈæŋ ʧˈAn hˈɛlps kənˈɛkt mˈɑdᵊlz tə jʊɹ ˈOn dˈATə.` | `lˈaŋ ʧˈAn hˈɛlps kənˈɛkt mˈɒdᵊlz tə jɔː ˈQn dˈAtə.` | `lˈaŋ tʃˈeɪn hˈɛlps kənˈɛkt mˈɒdəlz tə jɔːɹ ˈəʊn dˈeɪtə.` |
| Perplexity expanded its answer engine, and small voice models such as Kokoro run on a laptop. | `pəɹplˈɛksəTi ɪkspˈændᵻd ɪts ˈænsəɹ ˈɛnʤən, ænd smˈɔl vˈYs mˈɑdᵊlz sˈʌʧ æz kəkˈɔɹO ɹˈʌn ˌɔn ɐ lˈæptˌɑp.` | `pəplˈɛksɪti ɪkspˈandɪd ɪts ˈɑːnsə ˈɛnʤɪn, and smˈɔːl vˈYs mˈɒdᵊlz sˈʌʧ az kəkˈɔːɹQ ɹˈʌn ˌɒn ɐ lˈaptɒp.` | `pəplˈɛksɪtiʲ ɛkspˈandɪd ɪts ˈansəɹ ˈɛndʒɪn, and smˈɔːl vˈɔɪs mˈɒdəlz sˈʌtʃ ɐz kəkˈɔːɹəʊ ɹˈʌn ˌɒn ɐ lˈaptɒp.` |

## Files
- `results/model-manifest.json`: model files, revisions, sizes, SHA-256.
- `results/<candidate>/metrics.json`: all timings, PCM hashes per run, phonemes, the 20 offline runs. WAV files are local only.
- `results/summary.json`: machine summary including hardware.
- `listening/`: blind clips (local only), the sealed key, `INSTRUCTIONS.md`, `scoring-sheet.csv`.
