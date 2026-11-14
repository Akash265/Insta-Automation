# Runbook — manual Instagram publish (P1-15)

**When:** the soft launch, after gate G4, until Instagram API publishing (Phase 6). **Never during the 14-day experiment:** then the Reel goes only to the reader panel (`publication.method: private`).
**Who:** the founder, in the official Instagram app. No third-party posting tools and no shared passwords ([CLAUDE.md invariants](../../CLAUDE.md)).
**Precondition:** the edition is `approved` and deployed to production ([WORKFLOWS §7](../WORKFLOWS.md#7-phase-1-manual-runbook-no-n8n-no-database), steps 1–6). **A missing approval means no post.**

## 1. Reel spec checklist (tick before every upload)

`brief render` refuses to keep a Reel that fails the encoding, length or loudness checks below. This list confirms you upload that checked file, not an older or edited copy.

- [ ] File is `out/<issue_key>/<issue_key>.mp4` from today's `uv run --extra tts brief render editions/<date>.json --write`. It was not re-exported, trimmed or edited in another app.
- [ ] 1080×1920, 30 fps, H.264 High, yuv420p; AAC 48 kHz (the render report lists no problems).
- [ ] 35–90 s; audio and video lengths within 100 ms.
- [ ] Loudness −14 ± 1 LUFS; true peak ≤ −1 dBTP; no clipped samples.
- [ ] Watched in full once, with sound: no wrong card, no mispronounced name (fixes go in `video_templates/lexicon.yaml`, then re-render).
- [ ] Cover image is `out/<issue_key>/<issue_key>-cover.png`.
- [ ] `uv run brief validate editions/<date>.json --stage review` shows 0 blocking issues.
- [ ] The production issue page opens, and `/today/` points to it.

## 2. Caption

```
uv run brief caption editions/<date>.json --write      # stores it in the edition record
uv run brief caption editions/<date>.json --posting    # prints the exact text to paste
```
The caption is built from the same record as the Reel and the page (C09/C10). Paste it **unchanged**. A typo is fixed in the edition JSON and the caption regenerated, never only in the app. A sponsored edition must have its disclosure line in the caption (C11).

## 3. Upload (Instagram app, Professional account)

1. Move the MP4 and the cover PNG to the phone (AirDrop or cable, not a messaging app that re-compresses).
2. In the app, create a new **Reel** and select the MP4. Add no music, filters, stickers or text: the audio and on-screen text are part of the checked file.
3. Set the cover from the cover PNG if the app offers it; otherwise keep the first frame (it is the same intro card).
4. Paste the caption.
5. **Share**, and note the time.
6. Open the posted Reel and copy its link.

The bio link points to the site's `/today/` page, so it never needs editing per edition.

## 4. Record the publication (same day)

Add this block to `editions/<date>.json`:
```json
"publication": {
  "platform": "instagram",
  "method": "manual",
  "permalink": "https://www.instagram.com/reel/<code>/",
  "published_at": "2026-12-01T20:00:00+05:30"
}
```
Then:
```
uv run brief validate editions/<date>.json --stage published   # C01 needs the permalink for a manual post
git add editions/<date>.json && git commit -m "Edition <date> published"
```

## 5. If something goes wrong

- **Upload fails or hangs:** before retrying, check on the profile whether the Reel was posted. Never post a second copy blindly. If it was posted, record it. If not, retry once.
- **Wrong file or caption posted:** if editing the caption in the app fixes it, do that. Otherwise delete the post, re-post the checked file and write what happened in the edition's `review` notes. A factual error follows the [corrections policy](../../site_templates/pages/corrections-policy.html) and goes into the error log.
- **Instagram removes or restricts the Reel:** do not re-upload. Record it and decide at the weekly review.

## 6. First-time setup and test (P1-15 acceptance)

- [ ] Instagram Professional account created with the brand handle (needs P0-05), with two-factor authentication on. The password lives in your password manager, never in the repo or `.env`.
- [ ] Bio: one line from the promise, plus the site's `/today/` link.
- [ ] **One private test upload:** while the account is still private, render the fixture (`uv run --extra tts brief render tests/fixtures/editions/normal.json`, which writes `out/ADB-2026-11-20/`), run §1–§3, and confirm the cover, caption, sound and link. Then delete the test post.
- [ ] Test upload done on: ______
