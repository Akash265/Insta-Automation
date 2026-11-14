"""P1-01 tooling: `sources.yaml` validation, robots.txt matching and `brief sources check`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import brief.sources as sources_mod
from brief.cli import app
from brief.net import FetchResult
from brief.sources import (
    Source,
    SourceError,
    check_source,
    load_sources,
    parse_feed,
    parse_github_releases,
    robots_allows,
)
from tests.conftest import ROOT

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>a</title><pubDate>Fri, 13 Nov 2026 15:00:00 GMT</pubDate></item>
<item><title>b</title><pubDate>Thu, 12 Nov 2026 20:00:00 GMT</pubDate></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>
<entry><title>a</title><updated>2026-11-14T08:00:00Z</updated></entry></feed>"""
RDF = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>t</title></channel><item><title>a</title><dc:date>2026-11-13</dc:date></item>
</rdf:RDF>"""


def source(**kw: Any) -> Source:
    base: dict[str, Any] = {
        "key": "example-news",
        "name": "Example News",
        "publisher": "Example",
        "source_type": "rss",
        "tier": 1,
        "category": "model_release",
        "base_url": "https://example.com/news/",
        "feed_url": "https://example.com/news/rss.xml",
        "terms_note": "Official RSS feed; robots allowed.",
    }
    return Source.model_validate(base | kw)


def result(url: str, status: int | None = 200, body: bytes = b"", **kw: Any) -> FetchResult:
    return FetchResult(url, kw.pop("final_url", url), status, body, **kw)


def fake_fetcher(pages: dict[str, FetchResult]) -> Any:
    def get(url: str) -> FetchResult:
        return pages.get(url) or result(url, 404)

    return get


# --------------------------------------------------------------------------- the allow-list


def test_committed_allow_list_is_valid() -> None:
    srcs = load_sources(ROOT / "sources.yaml")
    enabled = [s for s in srcs if s.enabled]
    assert len(enabled) >= 20
    assert {s.tier for s in enabled} == {1, 2, 3}
    assert 4 <= sum(s.tier == 2 for s in enabled) <= 6  # EDITORIAL_PIPELINE §2
    assert all(s.category is None for s in enabled if s.tier == 3)
    assert not any(".atom" in (s.feed_url or "") for s in srcs if "github" in s.target)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"feed_url": "http://example.com/rss"}, "must be https"),
        ({"source_type": "html_page"}, "has no feed_url"),
        ({"feed_url": None}, "needs a feed_url"),
        (
            {"source_type": "github_releases", "feed_url": "https://github.com/o/r/releases.atom"},
            "api.github.com",
        ),
        ({"tier": 4}, "less than or equal to 3"),
        ({"key": "Bad Key"}, "pattern"),
        ({"fetch_interval_minutes": 5}, "greater than or equal to 15"),
    ],
)
def test_source_validation(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        source(**change)


def test_load_reports_duplicates_and_bad_yaml(tmp_path: Path) -> None:
    entry = {
        "key": "a",
        "name": "A",
        "publisher": "A",
        "source_type": "rss",
        "tier": 1,
        "base_url": "https://a.example/",
        "feed_url": "https://a.example/rss",
        "terms_note": "Official RSS feed.",
    }
    path = tmp_path / "sources.yaml"
    path.write_text(json.dumps({"sources": [entry, entry]}), encoding="utf-8")
    with pytest.raises(SourceError, match="duplicate key: a") as exc:
        load_sources(path)
    assert "duplicate feed_url" in str(exc.value)
    path.write_text("sources:\n  - key: a\n    terms_note: x: y\n", encoding="utf-8")
    with pytest.raises(SourceError, match="not valid YAML"):
        load_sources(path)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SourceError, match="no 'sources' list"):
        load_sources(path)


# --------------------------------------------------------------------------- robots.txt

HN = "User-Agent: *\nCrawl-delay: 30\nDisallow: /r?\nDisallow: /login\n"
GITHUB = "User-agent: *\nDisallow: /*.atom$\nAllow: /\n"


def test_robots_query_rule_is_not_a_prefix_rule() -> None:
    # urllib.robotparser treats `Disallow: /r?` as `/r` and wrongly blocks /rss
    assert robots_allows(HN, "https://news.ycombinator.com/rss")
    assert not robots_allows(HN, "https://news.ycombinator.com/r?id=1")
    assert not robots_allows(HN, "https://news.ycombinator.com/login")


def test_robots_wildcards_and_end_anchor() -> None:
    assert not robots_allows(GITHUB, "https://github.com/o/r/releases.atom")
    assert robots_allows(GITHUB, "https://github.com/o/r/releases.atom?x=1")  # `$` anchors
    assert robots_allows(GITHUB, "https://github.com/o/r/releases")


def test_robots_group_selection_and_precedence() -> None:
    text = (
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: Other\nAllow: /\n\n"
        "User-agent: AIDailyBrief\nDisallow: /private/\nAllow: /private/feed\n"
    )
    assert robots_allows(text, "https://x.example/news")  # our group, not `*`
    assert not robots_allows(text, "https://x.example/private/page")
    assert robots_allows(text, "https://x.example/private/feed.xml")  # longest match wins
    assert not robots_allows("User-agent: *\nDisallow: /\n", "https://x.example/a")
    assert robots_allows("User-agent: *\nDisallow:\n", "https://x.example/a")  # empty rule
    assert robots_allows("User-agent: *\nAllow: /a\nDisallow: /a\n", "https://x.example/a")
    assert robots_allows("", "https://x.example/a")


# --------------------------------------------------------------------------- feeds


def test_parse_feed_kinds_and_dates() -> None:
    rss = parse_feed(RSS)
    assert (rss.kind, rss.items) == ("rss", 2)
    assert rss.newest == datetime(2026, 11, 13, 15, 0, tzinfo=UTC)
    atom = parse_feed(ATOM)
    assert (atom.kind, atom.items, atom.newest) == (
        "atom", 1, datetime(2026, 11, 14, 8, 0, tzinfo=UTC))  # fmt: skip
    assert parse_feed(RDF).kind == "rdf" and parse_feed(RDF).items == 1
    with pytest.raises(ValueError, match="XML error"):
        parse_feed(b"<html><body>")
    with pytest.raises(ValueError, match="root element <html>"):
        parse_feed(b"<html></html>")


def test_hostile_xml_is_refused() -> None:
    entities = "".join(
        f'<!ENTITY {chr(98 + i)} "{("&" + chr(97 + i) + ";") * 10}">' for i in range(9)
    )
    bomb = f'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">{entities}]><rss>&j;</rss>'
    with pytest.raises(ValueError, match="XML error"):
        parse_feed(bomb.encode())
    xxe = (
        b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss>&x;</rss>'
    )
    with pytest.raises(ValueError, match="XML error"):
        parse_feed(xxe)


def test_parse_github_releases() -> None:
    body = json.dumps([{"tag_name": "v2", "published_at": "2026-11-09T18:21:19Z"},
                       {"tag_name": "v1", "published_at": None}]).encode()  # fmt: skip
    info = parse_github_releases(body)
    assert (info.kind, info.items) == ("github", 2)
    assert info.newest == datetime(2026, 11, 9, 18, 21, 19, tzinfo=UTC)
    with pytest.raises(ValueError, match="JSON array"):
        parse_github_releases(b'{"message": "rate limited"}')


# --------------------------------------------------------------------------- check_source

ROBOTS_OK = result("https://example.com/robots.txt", body=b"User-agent: *\nAllow: /\n",
                   content_type="text/plain")  # fmt: skip


def run(src: Source, *pages: FetchResult) -> sources_mod.SourceCheck:
    return check_source(src, fake_fetcher({p.url: p for p in pages}), NOW)


def test_check_passes_a_working_feed() -> None:
    c = run(source(), ROBOTS_OK, result("https://example.com/news/rss.xml", body=RSS))
    assert c.ok and not c.warnings and c.detail == "rss, 2 items, newest 2026-11-13"


def test_check_never_fetches_a_disallowed_url() -> None:
    robots = result("https://example.com/robots.txt", body=b"User-agent: *\nDisallow: /news/",
                    content_type="text/plain")  # fmt: skip
    seen: list[str] = []

    def get(url: str) -> FetchResult:
        seen.append(url)
        return robots if url.endswith("robots.txt") else result(url, body=RSS)

    c = check_source(source(), get, NOW)
    assert c.errors == ["robots.txt disallows this URL"]
    assert seen == ["https://example.com/robots.txt"]


ROBOTS_DOWN = result("https://example.com/robots.txt", None, error="ConnectTimeout")
ROBOTS_WALL = result("https://example.com/robots.txt", body=b"<html>verify</html>",
                     content_type="text/html")  # fmt: skip


@pytest.mark.parametrize(
    ("robots", "error", "warning"),
    [
        (result("https://example.com/robots.txt", 404), None, None),
        (result("https://example.com/robots.txt", 405), None, "returned 405"),
        (result("https://example.com/robots.txt", 503), "assume disallowed", None),
        (ROBOTS_DOWN, "assume disallowed", None),
        (ROBOTS_WALL, "bot wall", None),
    ],
)
def test_check_robots_status_rules(
    robots: FetchResult, error: str | None, warning: str | None
) -> None:
    c = run(source(), robots, result("https://example.com/news/rss.xml", body=RSS))
    assert (error in " ".join(c.errors)) if error else c.ok
    assert (warning in " ".join(c.warnings)) if warning else not c.warnings


def test_check_feed_problems() -> None:
    feed = "https://example.com/news/rss.xml"
    assert "declared rss, but the feed is atom" in run(
        source(), ROBOTS_OK, result(feed, body=ATOM)).errors  # fmt: skip
    assert run(source(), ROBOTS_OK, result(feed, 500)).errors == ["fetch failed: HTTP 500"]
    assert "size cap" in run(source(), ROBOTS_OK, result(feed, body=RSS, truncated=True)).errors[0]
    moved = run(source(), ROBOTS_OK, result(feed, body=RSS, final_url=feed + "?v=2"))
    assert moved.ok and "update the URL" in moved.warnings[0]
    old = RSS.replace(b"Nov 2026", b"Sep 2026")
    assert "older than 30 days" in run(source(), ROBOTS_OK, result(feed, body=old)).warnings[0]
    empty = b'<rss version="2.0"><channel><title>t</title></channel></rss>'
    assert "no items" in run(source(), ROBOTS_OK, result(feed, body=empty)).warnings[0]


def test_check_html_page() -> None:
    page = source(source_type="html_page", feed_url=None)
    ok = run(page, ROBOTS_OK, result(page.base_url, body=b"<html>", content_type="text/html"))
    assert ok.ok and ok.detail == "HTML page"
    bad = run(page, ROBOTS_OK, result(page.base_url, body=b"%PDF", content_type="application/pdf"))
    assert "expected an HTML page" in bad.errors[0]


# --------------------------------------------------------------------------- CLI


def test_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    missing = runner.invoke(app, ["sources", "check", "--file", str(tmp_path / "none.yaml")])
    assert missing.exit_code == 2
    unknown = runner.invoke(app, ["sources", "check", "--only", "no-such-source"])
    assert unknown.exit_code == 2 and "unknown source keys" in unknown.output

    def offline(url: str, policy: Any = None) -> FetchResult:
        if url.endswith("/robots.txt"):
            return result(url, 404)
        return result(url, body=RSS)

    monkeypatch.setattr(sources_mod, "fetch", offline)
    good = runner.invoke(app, ["sources", "check", "--only", "openai-news"])
    assert good.exit_code == 0 and "1 source(s) checked, 0 failed" in good.output
    bad = runner.invoke(app, ["sources", "check", "--only", "verge-ai"])  # atom, given RSS
    assert bad.exit_code == 1 and "FAIL verge-ai" in bad.output
