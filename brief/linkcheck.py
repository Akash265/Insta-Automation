"""`brief linkcheck` — check C02: every recorded source link returns HTTP 200 (task P1-04).

Collects the primary, supporting and evidence URLs of an edition, fetches each once
through the safe fetcher (redirects followed and checked hop by hop) and lists every
URL that does not end in HTTP 200.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

from brief.edition.schema import Edition
from brief.net import DEFAULT_POLICY, FetchPolicy, Resolver, fetch, system_resolver


@dataclass(frozen=True)
class LinkTarget:
    url: str
    where: tuple[str, ...]


@dataclass(frozen=True)
class LinkResult:
    url: str
    where: tuple[str, ...]
    status: int | None
    final_url: str
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200


def collect_links(edition: Edition) -> list[LinkTarget]:
    """Unique URLs in first-seen order, with every place each one is used."""
    places: dict[str, list[str]] = {}
    for s in sorted(edition.stories, key=lambda st: st.rank):
        places.setdefault(s.primary_source_url, []).append(f"story {s.rank} primary source")
        for u in s.supporting_source_urls:
            places.setdefault(u, []).append(f"story {s.rank} supporting source")
        for n, c in enumerate(s.claims, start=1):
            for e in c.evidence:
                places.setdefault(e.url, []).append(f"story {s.rank} claim {n} evidence")
    return [LinkTarget(url, tuple(dict.fromkeys(where))) for url, where in places.items()]


def check_links(
    targets: Sequence[LinkTarget],
    policy: FetchPolicy = DEFAULT_POLICY,
    resolver: Resolver = system_resolver,
    workers: int = 8,
) -> list[LinkResult]:
    with httpx.Client(follow_redirects=False) as client:

        def one(t: LinkTarget) -> LinkResult:
            r = fetch(t.url, policy, client=client, resolver=resolver, read_limit=1024)
            return LinkResult(t.url, t.where, r.status, r.final_url, r.error)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            return list(pool.map(one, targets))


def render_linkcheck(source: str, results: Sequence[LinkResult]) -> str:
    bad = [r for r in results if not r.ok]
    lines = [f"brief linkcheck: {source}", ""]
    if bad:
        lines.append(f"NOT OK ({len(bad)})")
        for r in bad:
            outcome = r.error or f"HTTP {r.status}"
            moved = f" -> {r.final_url}" if r.final_url != r.url else ""
            lines.append(f"  - {r.url}{moved}: {outcome}  [{'; '.join(r.where)}]")
    else:
        lines.append("NOT OK: none")
    lines += [
        "",
        f"RESULT: {'PASS' if not bad else 'FAIL'} "
        f"({len(results) - len(bad)} of {len(results)} links returned HTTP 200)",
    ]
    return "\n".join(lines)
