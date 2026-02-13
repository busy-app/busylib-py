from __future__ import annotations

import httpx
import pytest

from busylib import exceptions
from busylib.client import base
from busylib.settings import settings


class _SyncBaseClient(base.SyncClientBase):
    """
    Sync client wrapper to access protected _request in tests.
    """

    def __init__(self, transport: httpx.BaseTransport, *, max_retries: int = 0) -> None:
        """
        Initialize the client with a custom transport and retries.
        """
        super().__init__(
            addr="http://device.local",
            transport=transport,
            max_retries=max_retries,
            backoff=0.0,
        )


class _AsyncBaseClient(base.AsyncClientBase):
    """
    Async client wrapper to access protected _request in tests.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        """
        Initialize the client with a custom async transport.
        """
        super().__init__(
            addr="http://device.local",
            transport=transport,
            max_retries=0,
            backoff=0.0,
        )


def test_request_json_payload_requires_json_sync() -> None:
    """
    Validate JSON request headers and protocol error on invalid JSON response.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"].startswith("application/json")
        body = request.content.decode("utf-8")
        assert "Привет" in body
        return httpx.Response(200, text="ok", headers={"X-Request-ID": "rid-1"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    with pytest.raises(exceptions.BusyBarProtocolError) as exc:
        client._request("POST", "/api/test", json_payload={"msg": "Привет"})
    assert exc.value.request_id == "rid-1"
    assert exc.value.response_excerpt == "ok"


def test_request_json_payload_allow_text_sync() -> None:
    """
    Allow plain-text success payload when explicitly requested.
    """

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request("GET", "/api/test", allow_text=True)
    assert result == "ok"


def test_request_expect_bytes_sync() -> None:
    """
    Return raw bytes when expect_bytes is True.
    """

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"bin")

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request("GET", "/api/bin", expect_bytes=True)
    assert result == b"bin"


def test_request_transport_error_sync() -> None:
    """
    Convert transport errors into BusyBarRequestError when retries are exhausted.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _SyncBaseClient(httpx.MockTransport(responder))
    with pytest.raises(exceptions.BusyBarRequestError) as exc:
        client._request("GET", "/api/fail")
    assert exc.value.method == "GET"
    assert exc.value.path == "/api/fail"
    assert exc.value.attempts == 1


def test_cloud_mode_sets_bearer_header() -> None:
    """
    Ensure cloud mode triggers bearer authentication.

    This keeps cloud traffic on the Authorization header.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer token"
        return httpx.Response(200, json={"result": "OK"})

    transport = httpx.MockTransport(responder)
    client = base.SyncClientBase(
        addr=None,
        token="token",
        transport=transport,
        max_retries=0,
        backoff=0.0,
    )
    assert client.is_cloud is True
    client._request("GET", "/api/ping")
    client.close()


def test_local_available_uses_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure local availability check hits the configured base URL.

    This avoids mixing current client base_url with local probing.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://device.local/api/version"
        assert request.headers.get("x-api-token") == "token"
        return httpx.Response(200, json={"api_semver": "2.0.0"})

    monkeypatch.setattr(settings, "base_url", "http://device.local")
    transport = httpx.MockTransport(responder)
    client = base.SyncClientBase(
        addr="http://other.local",
        token="token",
        transport=transport,
        max_retries=0,
        backoff=0.0,
    )
    assert client.is_local_available() is True
    client.close()


@pytest.mark.asyncio
async def test_request_text_fallback_async() -> None:
    """
    Validate async request raises protocol error when JSON decoding fails.
    """

    async def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = _AsyncBaseClient(httpx.MockTransport(responder))
    with pytest.raises(exceptions.BusyBarProtocolError):
        await client._request("GET", "/api/test")
    await client.aclose()


@pytest.mark.asyncio
async def test_request_allow_text_async() -> None:
    """
    Allow plain-text success payload in async mode when explicitly requested.
    """

    async def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = _AsyncBaseClient(httpx.MockTransport(responder))
    result = await client._request("GET", "/api/test", allow_text=True)
    assert result == "ok"
    await client.aclose()


@pytest.mark.asyncio
async def test_request_expect_bytes_async() -> None:
    """
    Return raw bytes for async requests when expect_bytes is True.
    """

    async def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"bin")

    client = _AsyncBaseClient(httpx.MockTransport(responder))
    result = await client._request("GET", "/api/bin", expect_bytes=True)
    assert result == b"bin"
    await client.aclose()


@pytest.mark.asyncio
async def test_local_available_async(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure async local availability check hits the configured base URL.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://device.local/api/version"
        assert request.headers.get("x-api-token") == "token"
        return httpx.Response(200, json={"api_semver": "2.0.0"})

    monkeypatch.setattr(settings, "base_url", "http://device.local")
    transport = httpx.MockTransport(responder)
    client = base.AsyncClientBase(
        addr="http://other.local",
        token="token",
        transport=transport,
        max_retries=0,
        backoff=0.0,
    )
    assert await client.is_local_available() is True
    await client.aclose()
