# Editions

One file per day: `editions/YYYY-MM-DD.json`. This is the edition record and audit trail
(docs/EDITORIAL_PIPELINE.md §14). Start each day by copying the template:

```sh
cp editions/_template.json editions/2026-12-01.json   # then edit: issue_key, issue_date, cutoff_at, stories…
uv run brief validate editions/2026-12-01.json --stage draft     # after research and verification
uv run brief validate editions/2026-12-01.json --stage review    # before the 18:15 review
uv run brief validate editions/2026-12-01.json --stage published # after deploy and distribution
```

Stages: `draft` (sources and evidence), `review` (verified claims, score, script, caption,
rendered media), `published` (approved review, deployment and publication records).
Times always carry a timezone, and `event_at` (when it happened) stays separate from
`published_at` (when the article appeared). The JSON Schema is `schemas/edition.schema.json`
(regenerate with `uv run brief schema export`).
