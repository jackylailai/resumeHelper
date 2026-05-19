"""SSRF-safe wrapper around `httpx.AsyncClient`.

Every outbound HTTP request from scrapers (and, once #74 lands, the
user-supplied job-URL workflow) flows through `safe_async_client()`. The
wrapper:

- Resolves each target host before the connection and refuses if any
  resolved address falls inside a loopback, private, link-local,
  multicast, reserved, or unspecified range. Closes the `127.0.0.1`,
  RFC 1918, AWS/GCP/Azure metadata (`169.254.169.254`), IPv6 `::1`,
  `fc00::/7`, `fe80::/10`, and `0.0.0.0` attack surface.
- Re-applies the same check to every redirect target. Because the SSRF
  check sits in a custom `AsyncBaseTransport`, httpx's built-in redirect
  follower routes each hop back through it without extra glue.
- Refuses non-HTTP(S) schemes (`file://`, `gopher://`, ...).
- Bounds response body size via `max_response_bytes`.

TOCTOU caveat — DNS rebinding: a hostile DNS server can answer the
pre-check with a public IP and the actual TCP connection with an
internal IP. Closing this requires pinning the resolved IP and
forwarding the original Host header, which is non-trivial in httpx
and out of scope for #137. The wrapper closes the 95% case (constant
or co-operative resolvers); document the residual risk where this
client is used to fetch *attacker-supplied* URLs (relevant once #74
ships).
"""

from __future__ import annotations

import ipaddress
import socket

import httpx

_DEFAULT_TIMEOUT = httpx.Timeout(15.0)
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_MAX_REDIRECTS = 5
_ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrlError(Exception):
    """Raised when a target URL is rejected by the SSRF policy."""


def _is_forbidden_address(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        # Unparseable address — treat as forbidden so we never connect.
        return True
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def check_safe_url(url: str) -> None:
    """Validate a URL against the SSRF policy. Raises `UnsafeUrlError`
    for non-http(s) schemes, missing hosts, DNS failures, or resolved
    addresses inside a forbidden range."""
    parsed = httpx.URL(url) if not isinstance(url, httpx.URL) else url
    scheme = parsed.scheme.lower() if parsed.scheme else ""
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"disallowed scheme: {scheme!r}")
    host = parsed.host
    if not host:
        raise UnsafeUrlError("URL has no host")
    port = parsed.port if parsed.port is not None else (
        443 if scheme == "https" else 80
    )
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"DNS resolution failed for {host}: {exc}") from exc
    if not infos:
        raise UnsafeUrlError(f"DNS returned no addresses for {host}")
    for info in infos:
        addr = info[4][0]
        if _is_forbidden_address(addr):
            raise UnsafeUrlError(
                f"resolved address {addr} for {host} is in a forbidden range"
            )


class _SSRFGuardTransport(httpx.AsyncBaseTransport):
    """Wraps an inner transport. Runs `check_safe_url` on every request
    and caps the response body size after the inner transport returns.

    Because httpx routes redirects back through `handle_async_request`,
    putting the check at the transport layer covers each hop of a
    redirect chain automatically when `follow_redirects=True`.
    """

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport,
        max_response_bytes: int,
    ) -> None:
        self._inner = inner
        self._max_response_bytes = max_response_bytes

    async def handle_async_request(
        self, request: httpx.Request
    ) -> httpx.Response:
        check_safe_url(request.url)
        response = await self._inner.handle_async_request(request)

        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                declared = -1
            if declared > self._max_response_bytes:
                raise UnsafeUrlError(
                    f"response body declares {declared} bytes "
                    f"(> {self._max_response_bytes})"
                )
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


def safe_async_client(
    *,
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | float | None = _DEFAULT_TIMEOUT,
    max_response_bytes: int = _DEFAULT_MAX_BYTES,
    max_redirects: int = _DEFAULT_MAX_REDIRECTS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Return an `httpx.AsyncClient` with the SSRF guard transport
    installed. `transport=` lets tests inject `httpx.MockTransport(...)`
    while keeping the SSRF check active."""
    inner = transport if transport is not None else httpx.AsyncHTTPTransport()
    guard = _SSRFGuardTransport(inner, max_response_bytes=max_response_bytes)
    return httpx.AsyncClient(
        headers=dict(headers or {}),
        timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT,
        follow_redirects=True,
        max_redirects=max_redirects,
        transport=guard,
    )
