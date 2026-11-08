"""P1-04: the safe fetcher. No real internet access: a local test server and a fake DNS."""

from __future__ import annotations

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Response

from brief.net import DEFAULT_POLICY, BlockedURLError, FetchPolicy, check_url, fetch

# Lets the local test server (http://localhost) through; production policy never does.
LOCAL = FetchPolicy(
    allowed_schemes=frozenset({"http", "https"}),
    allowed_private_hosts=frozenset({"localhost", "127.0.0.1"}),
)


def public_dns(host: str, port: int) -> list[str]:
    return ["93.184.215.14"]


def loopback_dns(host: str, port: int) -> list[str]:
    return ["127.0.0.1"]


def no_dns(host: str, port: int) -> list[str]:
    raise OSError("no network in tests")


@pytest.mark.parametrize(
    "url",
    [
        "https://10.0.0.1/a",
        "https://192.168.1.10/a",
        "https://127.0.0.1/a",
        "https://169.254.169.254/latest/meta-data",
        "https://100.64.0.1/a",
        "https://[::1]/a",
        "https://[fd00::1]/a",
    ],
)
def test_private_and_special_addresses_blocked(url: str) -> None:
    with pytest.raises(BlockedURLError):
        check_url(url, DEFAULT_POLICY, no_dns)


def test_names_resolving_to_private_addresses_blocked() -> None:
    with pytest.raises(BlockedURLError, match="non-public"):
        check_url("https://localhost/", DEFAULT_POLICY, loopback_dns)


def test_public_address_allowed() -> None:
    check_url("https://example.com/a", DEFAULT_POLICY, public_dns)


@pytest.mark.parametrize("url", ["http://example.com/", "ftp://example.com/", "file:///etc/hosts"])
def test_only_https_by_default(url: str) -> None:
    with pytest.raises(BlockedURLError, match="scheme"):
        check_url(url, DEFAULT_POLICY, public_dns)


def test_credentials_in_url_blocked() -> None:
    with pytest.raises(BlockedURLError, match="credentials"):
        check_url("https://user:pass@example.com/", DEFAULT_POLICY, public_dns)


def test_unresolvable_host_blocked() -> None:
    with pytest.raises(BlockedURLError, match="resolve"):
        check_url("https://example.invalid/", DEFAULT_POLICY, no_dns)


def test_fetch_never_requests_blocked_url() -> None:
    result = fetch("https://10.0.0.1/a", DEFAULT_POLICY, resolver=no_dns)
    assert result.status is None and result.error and result.error.startswith("blocked")


def test_follows_redirects(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/a").respond_with_response(
        Response(status=302, headers={"Location": "/b"})
    )
    httpserver.expect_request("/b").respond_with_data("ok")
    result = fetch(httpserver.url_for("/a"), LOCAL)
    assert result.status == 200 and result.body == b"ok"
    assert result.final_url.endswith("/b") and len(result.redirects) == 1


def test_redirect_limit(httpserver: HTTPServer) -> None:
    for i in range(7):
        httpserver.expect_request(f"/r{i}").respond_with_response(
            Response(status=301, headers={"Location": f"/r{i + 1}"})
        )
    result = fetch(httpserver.url_for("/r0"), LOCAL)
    assert result.status is None and result.error and "too many redirects" in result.error


def test_redirect_to_private_address_blocked(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/hop").respond_with_response(
        Response(status=302, headers={"Location": "http://10.0.0.1/admin"})
    )
    result = fetch(httpserver.url_for("/hop"), LOCAL, resolver=no_dns)
    assert result.error and "non-public" in result.error
    assert result.final_url == "http://10.0.0.1/admin"


def test_body_is_capped(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/big").respond_with_data(b"x" * 3_000_000)
    policy = FetchPolicy(
        allowed_schemes=LOCAL.allowed_schemes,
        allowed_private_hosts=LOCAL.allowed_private_hosts,
        max_bytes=1_000_000,
    )
    result = fetch(httpserver.url_for("/big"), policy)
    assert result.truncated and len(result.body) == 1_000_000


def test_non_200_status_is_reported(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/gone").respond_with_data("no", status=404)
    assert fetch(httpserver.url_for("/gone"), LOCAL).status == 404
