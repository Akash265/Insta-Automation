# P1-05 licence evidence (licence gate, ADR-004)

Recorded 2026-11-08. Evidence is quoted from the **downloaded files at the exact revisions tested** and from
installed package metadata. The licence gate is a hard gate: any open doubt means **not passed** until resolved.

## Tested combinations

| Combination | Code licence | Weights / voice licence | Voice training data | Output restrictions stated | Licence gate |
|---|---|---|---|---|---|
| Kokoro-82M + `af_heart` | `kokoro` 0.9.4: Apache License (package metadata); repo LICENSE Apache-2.0 | Apache-2.0 (model card `license: apache-2.0`) | "trained exclusively on permissive/non-copyrighted audio data", including some CC BY 3.0/4.0 audio | None; the model card says it "has been deployed in numerous projects and commercial APIs" | **Pass**, with one low-risk note (CC BY attribution, below) |
| Kokoro-82M + `am_adam` | as above | as above (voice file in the same Apache-2.0 repo) | as above | as above | **Pass** (same note) |
| Kokoro-82M + `bf_emma` | as above | as above | as above | as above | **Pass** (same note) |
| Piper + `en_GB-cori-medium` | `piper-tts` 1.8.0: GPL-3.0-or-later (package metadata); repo COPYING GPL-3.0 | Voice MODEL_CARD: dataset "License: public domain" | "All recordings came from LibriVox.org", trained from scratch | Piper docs: "intended for personal use and text to speech research only" | **Not passed: unresolved.** Stays provisional (see below) |

## Evidence files (SHA-256)

- Kokoro model card `README.md`: `91dcabced89db6f109b8786642f50402d3ee87450e8189589b6f85520e7f4d78` (6,348 bytes, revision `f3ff3571791e39611d31c381e3a41a3af07b4987`)
  - "license: apache-2.0"
  - "With Apache-licensed weights, Kokoro can be deployed anywhere from production environments to personal projects."
  - "This is an Apache-licensed model, and Kokoro has been deployed in numerous projects and commercial APIs."
  - "Kokoro was trained exclusively on **permissive/non-copyrighted audio data** and IPA phoneme labels."
  - "The following CC BY audio was part of the dataset used to train Kokoro v1.0." (Koniwa, CC BY 3.0; SIWIS, CC BY 4.0)
- Kokoro weights `kokoro-v1_0.pth`: `496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4` (327,212,226 bytes, revision `f3ff3571791e39611d31c381e3a41a3af07b4987`)
- Kokoro voices: `af_heart.pt` `0ab5709b8ffab19bfd849cd11d98f75b60af7733253ad0d67b12382a102cb4ff` (523,425 bytes, revision `f3ff3571791e39611d31c381e3a41a3af07b4987`); `am_adam.pt` `ced7e284aba12472891be1da3ab34db84cc05cc02b5889535796dbf2d8b0cb34` (523,420 bytes, revision `f3ff3571791e39611d31c381e3a41a3af07b4987`); `bf_emma.pt` `d0a423deabf4a52b4f49318c51742c54e21bb89bbbe9a12141e7758ddb5da701` (523,420 bytes, revision `f3ff3571791e39611d31c381e3a41a3af07b4987`)
- Piper voice `en_GB-cori-medium.onnx`: `1899f98e5fb8310154f3c2973f4b8a929ba7245e722b3d3a85680b833d95f10d` (63,531,379 bytes, revision `e7229f7d33a10e145e109b886d661984201ac3c4`)
- Piper voice config `.onnx.json`: `e262c16d7f192f69d4edd6b4ef8a5915379e67495fcc402f1ab15eeb33da3d36` (4,966 bytes, revision `e7229f7d33a10e145e109b886d661984201ac3c4`)
- Piper `MODEL_CARD`: `38d76dfde845837b184668f8bab1c6426ad740b1af0fcebc349037822739e536` (474 bytes, revision `e7229f7d33a10e145e109b886d661984201ac3c4`)
  - "License: public domain"; "All recordings came from LibriVox.org."
- Piper docs (read 2026-11-08, https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md): "Piper is intended for personal use and text to speech research only" and "Some voices may have restrictive licenses".

## Supporting components (they affect software distribution, not the audio)

| Component | Version | Licence | Notes |
|---|---|---|---|
| `misaki` (Kokoro G2P) | 0.9.4 | Apache License | |
| `phonemizer-fork` | 3.3.2 | GNU GPL (package metadata) | Used by misaki |
| `espeakng-loader` | 0.2.4 | not declared in metadata | Ships the espeak-ng library that misaki actually uses |
| Homebrew `espeak-ng` | 1.52.0 | GPL-3.0-or-later (Homebrew formula metadata) | Installed as approved but **not used** by either engine here; both use bundled copies. Remove with `brew uninstall espeak-ng pcaudiolib` if wanted |
| `en_core_web_sm` (spaCy model) | 3.8.0 | MIT | Pinned in the lockfile so misaki never pip-installs it at runtime |
| `torch` | 2.14.1 | Apache-2.0 (and others) | |
| `onnxruntime` | 1.31.0 | MIT | Piper runtime |

GPL components (phonemizer-fork, espeak-ng, piper-tts) impose obligations when the software is **distributed**. The
pipeline is an internal service and is not distributed, and the generated audio is not covered. Re-review if that changes.

## Open items

1. **Piper intended-use statement (V-24) blocks the gate.** The cori voice data is public domain, but the Piper project
   describes itself as "intended for personal use and text to speech research only". To resolve: ask the Open Home
   Foundation maintainers in writing whether commercial narration with a public-domain voice is permitted, or get a legal
   opinion. Until then Piper is **provisional and not selectable**.
2. **Kokoro CC BY training audio (low risk).** CC BY licences require attribution for adaptations. It's unclear whether
   that reaches generated speech. Recommended precaution: credit "Voice: Kokoro TTS (Apache-2.0)" on the site's about page.
   This is a founder decision, not a blocker.
