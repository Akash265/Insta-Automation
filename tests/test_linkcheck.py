"""P1-04: `brief linkcheck` collects every recorded link and lists every non-200 URL."""

from __future__ import annotations

from typing import Any

from pytest_httpserver import HTTPServer

from brief.edition.schema import Edition
from brief.linkcheck import check_links, collect_links, render_linkcheck
from brief.net import FetchPolicy
from tests.conftest import load_fixture

LOCAL = FetchPolicy(
    allowed_schemes=frozenset({"http", "https"}),
    allowed_private_hosts=frozenset({"localhost", "127.0.0.1"}),
)


def test_collect_links_is_unique_and_labelled() -> None:
    edition = Edition.model_validate(load_fixture("normal"))
    targets = collect_links(edition)
    urls = [t.url for t in targets]
    assert len(urls) == len(set(urls))
    nimbus = next(t for t in targets if t.url == "https://example.com/labs/news/nimbus-2")
    assert "story 1 primary source" in nimbus.where
    assert "story 1 claim 2 evidence" in nimbus.where
    assert "https://example.com/corp/blog/support-assistant" in urls  # supporting source


def test_lists_every_non_200(httpserver: HTTPServer) -> None:
    from brief.linkcheck import LinkTarget

    httpserver.expect_request("/ok").respond_with_data("fine")
    httpserver.expect_request("/missing").respond_with_data("no", status=404)
    httpserver.expect_request("/forbidden").respond_with_data("no", status=403)
    targets = [
        LinkTarget(httpserver.url_for("/ok"), ("story 1 primary source",)),
        LinkTarget(httpserver.url_for("/missing"), ("story 2 primary source",)),
        LinkTarget(httpserver.url_for("/forbidden"), ("story 3 claim 1 evidence",)),
        LinkTarget("https://10.0.0.1/x", ("story 4 primary source",)),
    ]
    results = check_links(targets, LOCAL, workers=2)
    bad = {r.url for r in results if not r.ok}
    assert bad == {targets[1].url, targets[2].url, targets[3].url}
    text = render_linkcheck("edition.json", results)
    assert "HTTP 404" in text and "HTTP 403" in text and "blocked" in text
    assert "RESULT: FAIL (1 of 4 links returned HTTP 200)" in text


def test_all_ok_passes(httpserver: HTTPServer) -> None:
    from brief.linkcheck import LinkTarget

    data: dict[str, Any] = {}
    httpserver.expect_request("/ok").respond_with_data("fine")
    results = check_links([LinkTarget(httpserver.url_for("/ok"), ("x",))], LOCAL)
    assert all(r.ok for r in results) and not data
    assert "RESULT: PASS" in render_linkcheck("e.json", results)
