from __future__ import annotations

import json
import uuid

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
        assert "Café" in body
        return httpx.Response(200, text="ok", headers={"X-Request-ID": "rid-1"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    with pytest.raises(exceptions.BusyBarProtocolError) as exc:
        client._request("POST", "/api/test", json_payload={"msg": "Café"})
    assert exc.value.request_id == "rid-1"
    assert exc.value.response_excerpt == "ok"


def test_prepare_request_sync_returns_serialized_payload() -> None:
    """
    Build a prepared request with encoded JSON body and headers.

    This verifies request preparation can be used independently from execution.
    """
    client = _SyncBaseClient(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"result": "OK"}))
    )
    prepared = client.prepare_request(
        "POST",
        "/api/test",
        params={"x": "1"},
        json_payload={"msg": "Café"},
    )
    assert prepared.method == "POST"
    assert prepared.path == "/api/test"
    assert prepared.params == {"x": "1"}
    assert prepared.headers is not None
    assert prepared.headers["Content-Type"].startswith("application/json")
    assert isinstance(prepared.content, bytes)
    assert b"Caf" in prepared.content
    client.close()


def test_execute_prepared_request_with_external_sync_client() -> None:
    """
    Execute a prepared request using an injected external HTTPX client.

    This supports call-sites where request execution is delegated to pools.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"result": "OK"})

    client = _SyncBaseClient(
        httpx.MockTransport(lambda _request: httpx.Response(500, text="unused"))
    )
    prepared = client.prepare_request(
        "POST",
        "/api/test",
        json_payload={"value": 7},
    )
    with httpx.Client(
        base_url="http://external.local",
        transport=httpx.MockTransport(responder),
    ) as external_client:
        result = client.execute_prepared_request(prepared, client=external_client)
    assert result == {"result": "OK"}
    assert seen["url"] == "http://external.local/api/test"
    assert seen["body"] == '{"value":7}'
    client.close()


def test_request_json_payload_allow_text_sync() -> None:
    """
    Allow plain-text success payload when explicitly requested.
    """

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request("GET", "/api/test", allow_text=True)
    assert result == "ok"


def test_api_request_uses_client_session_sync() -> None:
    """
    Exposes raw API requests through the same client session.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/custom"
        assert request.headers["x-session-id"] == "bar-1"
        assert json.loads(request.content) == {
            "value": 1,
            "application_name": "app",
        }
        return httpx.Response(200, json={"result": "OK"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client.api_request(
        "POST",
        "/api/custom",
        session_id="bar-1",
        application_name="app",
        json_payload={"value": 1},
    )
    assert result == {"result": "OK"}


def test_request_applies_common_session_and_application_name_sync() -> None:
    """
    Adds shared request context as session header and application query param.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-session-id"] == "bar-1"
        assert dict(request.url.params) == {"application_name": "app"}
        return httpx.Response(200, json={"result": "OK"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request(
        "GET",
        "/api/test",
        session_id="bar-1",
        application_name="app",
    )
    assert result == {"result": "OK"}


def test_request_generates_request_id_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Adds X-Request-ID when caller did not provide one.
    """

    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=1))

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-request-id"] == uuid.UUID(int=1).hex
        return httpx.Response(200, json={"result": "OK"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request("GET", "/api/test")
    assert result == {"result": "OK"}


def test_request_preserves_caller_request_id_sync() -> None:
    """
    Keeps caller-provided X-Request-ID instead of generating a new value.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-request-id"] == "caller-rid"
        return httpx.Response(200, json={"result": "OK"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request(
        "GET",
        "/api/test",
        headers={"X-Request-ID": "caller-rid"},
    )
    assert result == {"result": "OK"}


def test_request_uses_generated_request_id_in_api_error_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Stores generated request id in API error when response has no own id.
    """

    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=2))

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    with pytest.raises(exceptions.BusyBarAPIError) as exc:
        client._request("POST", "/api/test", json_payload={"x": 1})
    assert exc.value.request_id == uuid.UUID(int=2).hex


def test_request_uses_generated_request_id_in_transport_error_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Stores generated request id in transport errors without a response.
    """

    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=3))

    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _SyncBaseClient(httpx.MockTransport(responder))
    with pytest.raises(exceptions.BusyBarRequestError) as exc:
        client._request("GET", "/api/fail")
    assert exc.value.request_id == uuid.UUID(int=3).hex


def test_request_applies_application_name_to_json_sync() -> None:
    """
    Adds application_name to JSON payload for mutating object requests.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {
            "path": "/ext/app.wav",
            "application_name": "app",
        }
        return httpx.Response(200, json={"result": "OK"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request(
        "POST",
        "/api/test",
        json_payload={"path": "/ext/app.wav"},
        application_name="app",
    )
    assert result == {"result": "OK"}


def test_request_keeps_application_name_in_params_for_binary_post_sync() -> None:
    """
    Adds application_name to query params when POST has no object JSON body.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"application_name": "app"}
        assert request.content == b"payload"
        return httpx.Response(200, json={"result": "OK"})

    client = _SyncBaseClient(httpx.MockTransport(responder))
    result = client._request(
        "POST",
        "/api/test",
        data=b"payload",
        application_name="app",
    )
    assert result == {"result": "OK"}


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
async def test_prepare_request_async_returns_serialized_payload() -> None:
    """
    Build an async prepared request with encoded JSON body and headers.

    This verifies async request preparation works without network execution.
    """
    client = _AsyncBaseClient(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"result": "OK"}))
    )
    prepared = client.prepare_request(
        "POST",
        "/api/test",
        params={"x": "1"},
        json_payload={"msg": "Café"},
    )
    assert prepared.method == "POST"
    assert prepared.path == "/api/test"
    assert prepared.params == {"x": "1"}
    assert prepared.headers is not None
    assert prepared.headers["Content-Type"].startswith("application/json")
    assert isinstance(prepared.content, bytes)
    assert b"Caf" in prepared.content
    await client.aclose()


@pytest.mark.asyncio
async def test_execute_prepared_request_with_external_async_client() -> None:
    """
    Execute a prepared async request using an injected external HTTPX client.

    This supports async call-sites where execution is delegated to pools.
    """
    seen: dict[str, object] = {}

    async def responder(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"result": "OK"})

    client = _AsyncBaseClient(
        httpx.MockTransport(lambda _request: httpx.Response(500, text="unused"))
    )
    prepared = client.prepare_request(
        "POST",
        "/api/test",
        json_payload={"value": 7},
    )
    async with httpx.AsyncClient(
        base_url="http://external.local",
        transport=httpx.MockTransport(responder),
    ) as external_client:
        result = await client.execute_prepared_request(prepared, client=external_client)
    assert result == {"result": "OK"}
    assert seen["url"] == "http://external.local/api/test"
    assert seen["body"] == '{"value":7}'
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
async def test_api_request_uses_client_session_async() -> None:
    """
    Exposes raw async API requests through the same client session.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/custom"
        assert request.headers["x-session-id"] == "bar-2"
        assert json.loads(request.content) == {
            "value": 2,
            "application_name": "app",
        }
        return httpx.Response(200, json={"result": "OK"})

    client = _AsyncBaseClient(httpx.MockTransport(responder))
    result = await client.api_request(
        "POST",
        "/api/custom",
        session_id="bar-2",
        application_name="app",
        json_payload={"value": 2},
    )
    assert result == {"result": "OK"}
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
