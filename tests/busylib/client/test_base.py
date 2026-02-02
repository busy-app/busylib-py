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


def test_json_bytes_preserves_utf8() -> None:
    """
    Ensure JSON serialization keeps UTF-8 characters unescaped.
    """
    payload = {"msg": "Привет"}
    data = base._json_bytes(payload)
    text = data.decode("utf-8")
    assert "Привет" in text
    assert "\\u041f" not in text


def test_data_length_handles_missing_len() -> None:
    """
    Return length for sized data and None for objects without __len__.
    """

    class _NoLen:
        """
        Dummy object without a length implementation.
        """

        pass

    assert base._data_length(b"abc") == 3
    assert base._data_length(_NoLen()) is None


def test_as_timeout_variants() -> None:
    """
    Ensure timeout normalization returns httpx.Timeout instances.
    """
    default_timeout = base._as_timeout(None)
    assert isinstance(default_timeout, httpx.Timeout)

    custom = base._as_timeout(2.5)
    assert isinstance(custom, httpx.Timeout)
    assert custom.read == 2.5

    existing = httpx.Timeout(1.0)
    assert base._as_timeout(existing) is existing


def test_request_json_payload_text_fallback_sync() -> None:
    """
    Validate JSON request headers and text fallback on invalid JSON response.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"].startswith("application/json")
        body = request.content.decode("utf-8")
        assert "Привет" in body
        return httpx.Response(200, text="ok")

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request("POST", "/api/test", json_payload={"msg": "Привет"})
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
    with pytest.raises(exceptions.BusyBarRequestError):
        client._request("GET", "/api/fail")


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
    Validate async request returns text when JSON decoding fails.
    """

    async def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = _AsyncBaseClient(httpx.MockTransport(responder))
    result = await client._request("GET", "/api/test")
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
