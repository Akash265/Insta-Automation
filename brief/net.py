"""Safe HTTP fetching for untrusted URLs (task P1-04).

Rules (docs/RISKS_AND_OPERATIONS.md §3.6):
- https only by default; URLs with embedded credentials are refused;
- every hop, including each redirect target, must resolve only to public
  (globally routable) addresses: private, loopback, link-local, reserved and
  carrier-grade NAT ranges are blocked (SSRF guard);
- at most 5 redirects, a per-request timeout, and a cap on bytes read.

Residual risk, accepted for this use (news and documentation sites): the address is
checked before the request, and the HTTP client resolves the name again when it
connects, so a DNS-rebinding host could still slip a private address in between.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
USER_AGENT = "AIDailyBrief/0.1 (link checker)"

Resolver = Callable[[str, int], list[str]]


class BlockedURLError(Exception):
    """The URL breaks the fetch policy and was not requested."""


@dataclass(frozen=True)
class FetchPolicy:
    allowed_schemes: frozenset[str] = frozenset({"https"})
    # Hosts exempt from the public-address rule. Empty in production; tests only.
    allowed_private_hosts: frozenset[str] = frozenset()
    max_redirects: int = 5
    max_bytes: int = 2_000_000
    timeout_s: float = 15.0
    user_agent: str = USER_AGENT


DEFAULT_POLICY = FetchPolicy()


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    status: int | None
    body: bytes = b""
    truncated: bool = False
    redirects: list[str] = field(default_factory=list)
    error: str | None = None
    content_type: str | None = None


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def check_url(
    url: str, policy: FetchPolicy = DEFAULT_POLICY, resolver: Resolver = system_resolver
) -> None:
    """Raise BlockedURLError if the URL breaks the policy. Resolves the host name."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in policy.allowed_schemes:
        raise BlockedURLError(f"scheme '{scheme or '(none)'}' is not allowed")
    if parts.username is not None or parts.password is not None:
        raise BlockedURLError("URLs with embedded credentials are not allowed")
    host = parts.hostname
    if not host:
        raise BlockedURLError("URL has no host")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise BlockedURLError(f"invalid port: {exc}") from exc
    if host in policy.allowed_private_hosts:
        return
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = resolver(host, port)
        except OSError as exc:
            raise BlockedURLError(f"cannot resolve host '{host}': {exc}") from exc
    if not addresses:
        raise BlockedURLError(f"host '{host}' did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global or ip.is_multicast:
            raise BlockedURLError(f"host '{host}' resolves to non-public address {ip}")


def _read_limited(response: httpx.Response, limit: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        if size + len(chunk) > limit:
            chunks.append(chunk[: limit - size])
            return b"".join(chunks), True
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks), False


def fetch(
    url: str,
    policy: FetchPolicy = DEFAULT_POLICY,
    client: httpx.Client | None = None,
    resolver: Resolver = system_resolver,
    read_limit: int | None = None,
) -> FetchResult:
    """GET a URL under the policy, following redirects manually so each hop is checked."""
    owns_client = client is None
    http = client or httpx.Client(follow_redirects=False)
    limit = policy.max_bytes if read_limit is None else min(read_limit, policy.max_bytes)
    redirects: list[str] = []
    current = url
    try:
        for _ in range(policy.max_redirects + 1):
            try:
                check_url(current, policy, resolver)
            except BlockedURLError as exc:
                return FetchResult(url, current, None, redirects=redirects, error=f"blocked: {exc}")
            try:
                with http.stream(
                    "GET",
                    current,
                    headers={"User-Agent": policy.user_agent},
                    timeout=policy.timeout_s,
                    follow_redirects=False,
                ) as resp:
                    location = resp.headers.get("location")
                    if resp.status_code in REDIRECT_CODES and location:
                        current = urljoin(current, location)
                        redirects.append(current)
                        continue
                    body, truncated = _read_limited(resp, limit)
                    return FetchResult(
                        url,
                        current,
                        resp.status_code,
                        body,
                        truncated,
                        redirects,
                        None,
                        resp.headers.get("content-type"),
                    )
            except httpx.HTTPError as exc:
                return FetchResult(
                    url, current, None, redirects=redirects, error=f"{type(exc).__name__}: {exc}"
                )
        return FetchResult(
            url,
            current,
            None,
            redirects=redirects,
            error=f"too many redirects (more than {policy.max_redirects})",
        )
    finally:
        if owns_client:
            http.close()
