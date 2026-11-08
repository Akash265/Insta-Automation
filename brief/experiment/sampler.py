"""Seeded audit sampler (task P1-19): which stories the auditor checks for an edition.

The choice is seeded from the issue key, so anyone can reproduce it and it cannot be
picked after seeing which stories look weakest (docs/VALIDATION_EXPERIMENT.md §6.2).
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence


def sample_story_ranks(issue_key: str, ranks: Sequence[int], k: int = 2) -> list[int]:
    seed = int(hashlib.sha256(issue_key.encode("utf-8")).hexdigest(), 16)
    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not security
    pool = sorted(set(ranks))
    return sorted(rng.sample(pool, min(k, len(pool))))
