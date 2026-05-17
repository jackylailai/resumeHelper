"""Unit tests for the SSRF-safe HTTP client wrapper (#137).

The guard transports sit in front of every outbound HTTP call from the
scrapers (and, once #74 ships, the user-supplied URL workflow). Tests
cover:

- direct address-policy checks (`_is_forbidden_address`)
- URL-level pre-checks (`check_safe_url`) with monkeypatched DNS
- end-to-end `safe_async_client` against an `httpx.MockTransport` for
  the redirect-rechecks-each-hop case
- non-http(s) scheme rejection
- response body size cap via Content-Length
"""

from __future__ import annotations

import socket

import httpx
import pytest

from backend.app.services.http.safe_client import (
    UnsafeUrlError,
    _is_forbidden_address,
    check_safe_url,
    safe_async_client,
)


@pytest.mark.parametrize(
    "addr",
    [
        "127.0.0.1",
        "0.0.0.0",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff00::1",
    ],
)
def test_forbidden_address_ranges_rejected(addr: str) -> None:
    assert _is_forbidden_address(addr) is True


@pytest.mark.parametrize(
    "addr",
    ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"],
)
def test_public_addresses_allowed(addr: str) -> None:
    assert _is_forbidden_address(addr) is False


def test_check_safe_url_rejects_non_http_scheme() -> None:
    with pytest.raises(UnsafeUrlError):
        check_safe_url("file:///etc/passwd")
    with pytest.raises(UnsafeUrlError):
        check_safe_url("gopher://example.com")


def test_check_safe_url_rejects_missing_host() -> None:
    with pytest.raises(UnsafeUrlError):
        check_safe_url("http:///path")


def _stub_getaddrinfo(addr: str):
    def _fake(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (addr, port or 0))]

    return _fake


def test_check_safe_url_rejects_loopback_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _stub_getaddrinfo("127.0.0.1"))
    with pytest.raises(UnsafeUrlError):
        check_safe_url("http://attacker.example/x")


def test_check_safe_url_rejects_metadata_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _stub_getaddrinfo("169.254.169.254"))
    with pytest.raises(UnsafeUrlError):
        check_safe_url("http://metadata.attacker.example/latest/meta-data/")


def test_check_safe_url_rejects_rfc1918_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _stub_getaddrinfo("10.0.0.5"))
    with pytest.raises(UnsafeUrlError):
        check_safe_url("http://internal.attacker.example/x")


def test_check_safe_url_accepts_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _stub_getaddrinfo("8.8.8.8"))
    check_safe_url("http://example.com/x")


def test_check_safe_url_rejects_dns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*args, **kwargs):
        raise socket.gaierror("nodename nor servname provided")

    monkeypatch.setattr(socket, "getaddrinfo", _fail)
    with pytest.raises(UnsafeUrlError):
        check_safe_url("http://does-not-exist.example/x")


@pytest.mark.asyncio
async def test_safe_async_client_blocks_loopback_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _stub_getaddrinfo("127.0.0.1"))

    def handler(request: httpx.Request) -> httpx.Response:
        # The SSRF guard should refuse before reaching this handler.
        raise AssertionError("inner transport should never be called")

    transport = httpx.MockTransport(handler)
    async with safe_async_client(transport=transport) as client:
        with pytest.raises(UnsafeUrlError):
            await client.get("http://attacker.example/x")


@pytest.mark.asyncio
async def test_safe_async_client_blocks_redirect_to_internal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public URL that 302-redirects to an internal host must be
    rejected on the redirect hop."""
    resolved = {"public.example": "8.8.8.8", "internal.example": "10.0.0.5"}

    def fake_getaddrinfo(host, port, *args, **kwargs):
        addr = resolved.get(host)
        if addr is None:
            raise socket.gaierror(f"unknown host {host}")
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (addr, port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(
                302, headers={"Location": "http://internal.example/secret"}
            )
        raise AssertionError(
            f"second hop should be blocked by SSRF check, got {request.url}"
        )

    transport = httpx.MockTransport(handler)
    async with safe_async_client(transport=transport) as client:
        with pytest.raises(UnsafeUrlError):
            await client.get("http://public.example/x")


@pytest.mark.asyncio
async def test_safe_async_client_allows_public_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _stub_getaddrinfo("8.8.8.8"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with safe_async_client(transport=transport) as client:
        response = await client.get("https://www.example.com/data")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_safe_async_client_caps_response_body_via_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _stub_getaddrinfo("8.8.8.8"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": "999999999"},
            content=b"X" * 16,
        )

    transport = httpx.MockTransport(handler)
    async with safe_async_client(
        transport=transport, max_response_bytes=1024
    ) as client:
        with pytest.raises(UnsafeUrlError):
            await client.get("https://www.example.com/big")
