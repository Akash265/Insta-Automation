# Editorial Charter — AI Daily Brief

Status: **DRAFT for founder approval (P1-01, G1 M1).** One page, per the business plan's Phase 0 exit criterion. It restates approved rules; where it is shorter than [EDITORIAL_PIPELINE](EDITORIAL_PIPELINE.md), that document governs.

## 1. Promise and audience
**Promise** (business plan §2): "The AI developments worth knowing today — clearly explained, linked to the original sources, and delivered in one short briefing."

**For:** AI builders and developers, and technology professionals and students (primary); founders, product managers and the AI-curious public (secondary). English-language, India-based, written for a global English-speaking audience.

## 2. Scope
- **In:** model and product releases, research, open-source releases, AI business (deployments, funding, infrastructure, pricing) and AI policy and regulation. Each story gets exactly one category: `model_release`, `research`, `open_source`, `business` or `policy`.
- **Out:** stories that are not about AI or are purely promotional (R06); rumours, leaks and predictions without responsible attributed reporting (R04); stories centred on a private individual's personal data (R11); anything only on a login-walled or bot-protected page.
- **Not a promise to cover everything.** We publish 5–7 stories, fewer on a quiet day (at least 3 for a Reel, otherwise web-only or skip). We never add filler.

## 3. Sourcing
- **Tiers** ([EDITORIAL_PIPELINE §2](EDITORIAL_PIPELINE.md#2-source-hierarchy-and-initial-allow-list)): tier 1 (primary) establishes a claim; tier 2 (credible publication) establishes one only with attribution, and needs corroboration if contentious or high-impact; tier 3 (discovery) **never** does.
- **Allow-list:** `sources.yaml`. It has 27 sources, which is about 20 once the five GitHub repos count as one group. They are 22 tier 1 (12 labs and companies, arXiv, 5 GitHub repos, 4 policy bodies), 4 tier 2 (The Verge, TechCrunch, MIT Technology Review, WIRED) and 1 tier 3 (Hacker News). On 2026-11-14 every source passed `uv run brief sources check`: robots.txt allows our URL, and the feed or page fetches and parses.
- **What we take:** title, link, dates, a summary of at most 1,000 characters and verification excerpts of at most 300 characters. We write the copy in our own words (at most 1 sentence verbatim, R09) and always link the original. We never bypass logins, paywalls or bot protection.
- **Candidates checked and left out (2026-11-14):**
  - **Ars Technica:** robots.txt is behind a bot-verification wall, so we cannot confirm access.
  - **The Register:** robots.txt disallows the feed's API URL.
  - **VentureBeat:** HTTP 429 (rate-limited).
  - **IEEE Spectrum:** the connection timed out.
  - **GitHub `.atom` release feeds:** github.com's robots.txt disallows `/*.atom$`. We use the GitHub REST API instead.
  - **Reddit:** not probed. Its Data API terms would need their own review before any use.
  - **Reuters and Bloomberg:** not probed. Neither is known to offer a public feed; either can be added later if one is found and passes the check.
- **Changes:** adding or removing a source is a founder decision, recorded in `sources.yaml` and re-checked with `brief sources check`. Sources are disabled, never deleted. The GitHub repo list is reviewed monthly.

## 4. Editorial rules
- **Every material claim has evidence** (tier 1, or attributed tier 2) and a verification status. *Discovered* is never the same as *verified*.
- **Dates:** we keep the event date and the publication date separate. Time words must match the event date: "today" only for today's events; weekend stories say the day ("On Saturday").
- **Vendor claims are labelled** as vendor claims ("Example Labs says…"). A vendor benchmark is never presented as an independent result (R08).
- **No invented links:** every URL in our copy comes from a fetched source record (R02). The AI model never writes citations.
- **Selection:** rubric v1.1 (100 points), eligibility ≥ 55 and hard rules R01–R12 ([EDITORIAL_PIPELINE §5–§6](EDITORIAL_PIPELINE.md#5-ranking--the-100-point-rubric-briefintelscorepy-score_version--11)). The threshold is frozen for the 14-day experiment.
- **Human approval:** a person approves every edition before it is published. There is no time-out publishing.
- **Corrections:** errors are corrected openly. A correction note goes on the issue page and is never silently overwritten ([corrections policy](../site_templates/pages/corrections-policy.html)).
- **AI use and voice:** AI may help draft copy from verified claims only. The narration is a synthetic voice (Kokoro `am_adam`). Both are disclosed on the About page.
- **Independence:** sponsored or affiliate content is always disclosed (R10). Selection is never sold.

## 5. Style
- Plain English, present tense for facts, no hype ("revolutionary", "game-changing"), and restrained wording.
- Every story has one concrete **"why it matters"** sentence and, where relevant, its limitations.
- Company and model names are spelled exactly as the primary source spells them.
- **Reel:** 35–90 s; hook (brand, date, promise) → lead story → stories 2–5 → optional 6–7 → takeaway and CTA ("Full stories and original links — link in bio"). Card text stays within the C09 limits.
- **Every edition** has an issue page with publisher, event and publication dates, and a "Read original" link for each story.

## 6. Approval
| Item | Decision | Founder | Date |
|---|---|---|---|
| This charter | ☐ approved as written / ☐ approved with changes noted here | | |
| `sources.yaml` (27 sources) | ☐ approved / ☐ approved with these changes: | | |
