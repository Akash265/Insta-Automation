"""The source allow-list (`sources.yaml`, task P1-01) and `brief sources check`.

Each source mirrors a row of the `sources` table (docs/DATABASE_DESIGN.md §4.1), so the
Phase 2 `brief sources sync` can load the same file. `brief sources check` makes web
requests through the safe fetcher (brief/net.py): for every enabled source it reads the
host's robots.txt (RFC 9309, our own matcher, because `urllib.robotparser` misreads rules
such as `Disallow: /r?` as `/r`), then fetches the feed or page and checks that it parses.

Feed XML is untrusted. It is parsed with the standard library after the fetcher's size
cap; expat >= 2.4.1 (checked at import) refuses external entities and limits entity
expansion (billion laughs), so `defusedxml` is not needed.
"""

from __future__ import annotations

import json
import pyexpat
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from brief.net import FetchPolicy, FetchResult, fetch

DEFAULT_SOURCES = Path("sources.yaml")
ROBOTS_TOKEN = "AIDailyBrief"  # noqa: S105 (product token in our User-Agent, not a secret)
FEED_POLICY = FetchPolicy(user_agent="AIDailyBrief/0.1 (feed checker)")
STALE_AFTER = timedelta(days=30)

SourceType = Literal["rss", "atom", "github_releases", "arxiv", "html_page"]
Category = Literal["model_release", "research", "open_source", "business", "policy"]
FEED_TYPES = frozenset({"rss", "atom", "github_releases", "arxiv"})
GITHUB_API_RE = re.compile(r"^https://api\.github\.com/repos/[\w.-]+/[\w.-]+/releases(\?[\w=&]*)?$")
EXPECTED_KIND = {"rss": ("rss", "rdf"), "arxiv": ("rss", "rdf"), "atom": ("atom",),
                 "github_releases": ("github",)}  # fmt: skip


# xml.etree is safe for untrusted feeds only with expat >= 2.4.1, which refuses external
# entities and caps entity amplification (Python docs, "XML vulnerabilities"). Tested.
if pyexpat.version_info < (2, 4, 1):  # pragma: no cover
    raise ImportError(f"expat {pyexpat.EXPAT_VERSION} is too old to parse untrusted feeds")


class SourceError(ValueError):
    """`sources.yaml` is invalid."""


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    source_type: SourceType
    tier: int = Field(ge=1, le=3)
    category: Category | None = None
    base_url: str
    feed_url: str | None = None
    fetch_interval_minutes: int = Field(default=60, ge=15)
    enabled: bool = True
    terms_note: str = Field(min_length=10)
    notes: str | None = None

    @model_validator(mode="after")
    def _urls(self) -> Source:
        for label, url in (("base_url", self.base_url), ("feed_url", self.feed_url)):
            if url is not None and urlsplit(url).scheme != "https":
                raise ValueError(f"{label} must be https: {url}")
        if self.source_type == "html_page" and self.feed_url is not None:
            raise ValueError("an html_page source has no feed_url (base_url is the page)")
        if self.source_type in FEED_TYPES and self.feed_url is None:
            raise ValueError(f"a {self.source_type} source needs a feed_url")
        if self.source_type == "github_releases" and not GITHUB_API_RE.match(self.feed_url or ""):
            raise ValueError(
                "github_releases must use https://api.github.com/repos/OWNER/REPO/releases "
                "(github.com's robots.txt disallows the .atom feeds)"
            )
        return self

    @property
    def target(self) -> str:
        """The URL the pipeline reads."""
        return self.feed_url or self.base_url


def load_sources(path: Path = DEFAULT_SOURCES) -> list[Source]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SourceError(f"{path}: not valid YAML ({exc})") from exc
    raw = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(raw, list) or not raw:
        raise SourceError(f"{path}: no 'sources' list")
    sources: list[Source] = []
    problems: list[str] = []
    for i, item in enumerate(raw):
        try:
            sources.append(Source.model_validate(item))
        except ValidationError as exc:
            key = item.get("key", f"#{i + 1}") if isinstance(item, dict) else f"#{i + 1}"
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"]) or "source"
                problems.append(f"{key}: {loc}: {err['msg']}")
    for label, values in (
        ("key", [s.key for s in sources]),
        ("feed_url", [s.feed_url for s in sources if s.feed_url]),
    ):
        dupes = sorted({v for v in values if values.count(v) > 1})
        if dupes:
            problems.append(f"duplicate {label}: {', '.join(dupes)}")
    if problems:
        raise SourceError(f"{path}:\n  " + "\n  ".join(problems))
    return sources


# --------------------------------------------------------------------------- robots.txt


def _groups(text: str) -> list[tuple[list[str], list[tuple[bool, str]]]]:
    """(user-agents, [(allow, pattern)]) groups, per RFC 9309 §2.1."""
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    in_rules = False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        name, value = (part.strip() for part in line.split(":", 1))
        name = name.lower()
        if name == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(value.lower())
        elif name in ("allow", "disallow") and agents:
            in_rules = True
            if value:  # an empty Disallow allows everything
                rules.append((name == "allow", value))
    if agents:
        groups.append((agents, rules))
    return groups


def _pattern_matches(pattern: str, path: str) -> bool:
    regex = re.escape(pattern).replace(r"\*", ".*")
    if regex.endswith(r"\$"):
        regex = regex[:-2] + "$"
    return re.match(regex, path) is not None


def robots_allows(text: str, url: str, token: str = ROBOTS_TOKEN) -> bool:
    """RFC 9309: our group (else `*`), longest matching rule wins, Allow wins a tie."""
    parts = urlsplit(url)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    groups = _groups(text)
    mine = [r for agents, r in groups if token.lower() in agents]
    if mine:
        rules = [rule for r in mine for rule in r]
    else:
        rules = [rule for agents, r in groups if "*" in agents for rule in r]
    best: tuple[int, bool] | None = None
    for allow, pattern in rules:
        if _pattern_matches(pattern, path):
            rank = (len(pattern), allow)
            if best is None or rank > best:
                best = rank
    return True if best is None else best[1]


# --------------------------------------------------------------------------- feeds


@dataclass(frozen=True)
class FeedInfo:
    kind: str  # rss | atom | rdf
    items: int
    newest: datetime | None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _date(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            value = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def parse_feed(body: bytes) -> FeedInfo:
    """Count items and find the newest date in an RSS, Atom or RDF feed."""
    try:
        root = ET.fromstring(body)  # noqa: S314 (expat >= 2.4.1, checked at import)
    except ET.ParseError as exc:
        raise ValueError(f"not a feed (XML error: {exc})") from exc
    kind = {"rss": "rss", "feed": "atom", "RDF": "rdf"}.get(_local(root.tag))
    if kind is None:
        raise ValueError(f"not a feed (root element <{_local(root.tag)}>)")
    entries = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    dates: list[datetime] = []
    for entry in entries:
        for child in entry:
            if _local(child.tag) in ("pubDate", "published", "updated", "date"):
                parsed = _date(child.text)
                if parsed:
                    dates.append(parsed)
    return FeedInfo(kind, len(entries), max(dates) if dates else None)


def parse_github_releases(body: bytes) -> FeedInfo:
    """The GitHub REST API releases list (a JSON array with `published_at`)."""
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise ValueError(f"not a GitHub releases list (JSON error: {exc})") from exc
    if not isinstance(data, list):
        raise ValueError("not a GitHub releases list (expected a JSON array)")
    dates = [d for r in data if isinstance(r, dict) if (d := _date(r.get("published_at")))]
    return FeedInfo("github", len(data), max(dates) if dates else None)


# --------------------------------------------------------------------------- check


Fetcher = Callable[[str], FetchResult]


@dataclass
class SourceCheck:
    key: str
    target: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


def _robots(target: str, fetcher: Fetcher, cache: dict[str, FetchResult]) -> FetchResult:
    parts = urlsplit(target)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in cache:
        cache[origin] = fetcher(f"{origin}/robots.txt")
    return cache[origin]


def check_source(
    source: Source,
    fetcher: Fetcher,
    now: datetime,
    robots_cache: dict[str, FetchResult] | None = None,
) -> SourceCheck:
    result = SourceCheck(source.key, source.target)
    cache = {} if robots_cache is None else robots_cache
    robots = _robots(source.target, fetcher, cache)
    if robots.status == 200:
        if "html" in (robots.content_type or "").lower():
            result.errors.append("robots.txt is an HTML page (bot wall?); cannot confirm access")
        elif not robots_allows(robots.body.decode("utf-8", "replace"), source.target):
            result.errors.append("robots.txt disallows this URL")
    elif robots.status is not None and 400 <= robots.status < 500:
        if robots.status not in (404, 410):
            result.warnings.append(
                f"robots.txt returned {robots.status}; treated as no rules (RFC 9309), review"
            )
    else:
        why = robots.error or f"HTTP {robots.status}"
        result.errors.append(f"robots.txt unreachable ({why}); RFC 9309 says assume disallowed")
    if result.errors:
        return result

    page = fetcher(source.target)
    if page.status != 200:
        result.errors.append(f"fetch failed: {page.error or f'HTTP {page.status}'}")
        return result
    if page.truncated:
        result.errors.append("response larger than the fetch size cap")
        return result
    if page.final_url != source.target:
        result.warnings.append(f"redirects to {page.final_url}; update the URL")
    if source.source_type == "html_page":
        if "html" not in (page.content_type or "").lower():
            result.errors.append(f"expected an HTML page, got {page.content_type}")
        else:
            result.detail = "HTML page"
        return result
    try:
        if source.source_type == "github_releases":
            info = parse_github_releases(page.body)
        else:
            info = parse_feed(page.body)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result
    if info.kind not in EXPECTED_KIND[source.source_type]:
        result.errors.append(f"declared {source.source_type}, but the feed is {info.kind}")
    newest = info.newest.astimezone(UTC).date().isoformat() if info.newest else "no dates"
    result.detail = f"{info.kind}, {info.items} items, newest {newest}"
    if info.items == 0:
        result.warnings.append("feed has no items right now (arXiv is empty at weekends)")
    elif info.newest and now - info.newest > STALE_AFTER:
        result.warnings.append(f"newest item is older than {STALE_AFTER.days} days")
    return result


def check_sources(
    sources: list[Source],
    now: datetime,
    fetcher: Fetcher | None = None,
    only: set[str] | None = None,
) -> list[SourceCheck]:
    def default_fetch(url: str) -> FetchResult:
        result = fetch(url, FEED_POLICY)
        return fetch(url, FEED_POLICY) if result.status is None else result  # one retry

    get = fetcher or default_fetch
    cache: dict[str, FetchResult] = {}
    return [
        check_source(s, get, now, cache)
        for s in sources
        if s.enabled and (only is None or s.key in only)
    ]


def render_checks(checks: list[SourceCheck]) -> str:
    lines = []
    for c in checks:
        mark = "FAIL" if c.errors else ("WARN" if c.warnings else "ok  ")
        lines.append(f"{mark} {c.key:28} {c.detail}")
        lines += [f"       error: {e}" for e in c.errors]
        lines += [f"       warning: {w}" for w in c.warnings]
    failed = sum(1 for c in checks if c.errors)
    lines.append(f"\n{len(checks)} source(s) checked, {failed} failed")
    return "\n".join(lines)
