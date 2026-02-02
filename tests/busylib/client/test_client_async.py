import httpx
import pytest

from busylib import AsyncBusyBar, exceptions, types


def make_client(async_responder, **kwargs) -> AsyncBusyBar:
    """
    Build an async BusyBar client backed by HTTPX MockTransport.

    Uses async responders without extra transport configuration.
    """
    transport = httpx.MockTransport(async_responder)
    return AsyncBusyBar(addr="http://device.local", transport=transport, **kwargs)


@pytest.mark.asyncio
async def test_get_version_success_async():
    """
    Parse version information from the async client.

    Ensures the response is mapped to VersionInfo.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(200, json={"api_semver": "2.0.0", "branch": "dev"})

    client = make_client(responder, api_version="2.0.0")
    result = await client.get_version()
    assert isinstance(result, types.VersionInfo)
    assert result.api_semver == "2.0.0"
    await client.aclose()


@pytest.mark.asyncio
async def test_get_device_name_and_time_async():
    """
    Fetch name and time via async client calls.

    Confirms both endpoints return parsed models.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/name":
            return httpx.Response(200, json={"name": "BusyBar"})
        if request.url.path == "/api/time":
            return httpx.Response(200, json={"timestamp": "2024-01-01T10:00:00"})
        return httpx.Response(404, json={"error": "missing", "code": 404})

    client = make_client(responder)
    name = await client.get_device_name()
    assert name.name == "BusyBar"
    time_info = await client.get_device_time()
    assert time_info.timestamp == "2024-01-01T10:00:00"
    await client.aclose()


@pytest.mark.asyncio
async def test_get_account_info_async():
    """
    Parse linked account info from the async client.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/info"
        return httpx.Response(200, json={"linked": False, "email": "name@example.com"})

    client = make_client(responder)
    result = await client.get_account_info()
    assert result.linked is False
    assert result.email == "name@example.com"
    await client.aclose()


@pytest.mark.asyncio
async def test_get_account_status_async():
    """
    Parse MQTT account state from the async client.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/status"
        return httpx.Response(200, json={"state": "connected"})

    client = make_client(responder)
    result = await client.get_account_status()
    assert result.state == "connected"
    await client.aclose()


@pytest.mark.asyncio
async def test_link_account_async():
    """
    Parse account link response from the async client.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/link"
        return httpx.Response(200, json={"code": "EFGH", "expires_at": 1700000001})

    client = make_client(responder)
    result = await client.link_account()
    assert result.code == "EFGH"
    assert result.expires_at == 1700000001
    await client.aclose()


@pytest.mark.asyncio
async def test_async_retry_on_transport_error():
    """
    Retry transport failures for async requests.

    Validates that a second attempt succeeds.
    """
    calls = {"count": 0}

    async def responder(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("fail", request=request)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder, max_retries=1, backoff=0.0)
    resp = await client.enable_wifi()
    assert resp.result == "OK"
    assert calls["count"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_draw_on_display_utf8_async():
    """
    Ensure async display payloads preserve UTF-8 content.

    Verifies non-ASCII text is not escaped.
    """
    payload = {
        "app_id": "demo",
        "elements": [
            {
                "id": "1",
                "type": "text",
                "x": 0,
                "y": 0,
                "text": "Привет",
                "display": "front",
            }
        ],
    }

    async def responder(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert "Привет" in body
        assert "\\u041f" not in body
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = await client.draw_on_display(payload)
    assert resp.result == "OK"
    await client.aclose()


@pytest.mark.asyncio
async def test_error_response_raises_api_error_async():
    """
    Raise BusyBarAPIError for async error responses.

    Confirms JSON error payloads are surfaced.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request", "code": 400})

    client = make_client(responder)
    with pytest.raises(exceptions.BusyBarAPIError):
        await client.get_status()
    await client.aclose()


@pytest.mark.asyncio
async def test_async_set_display_brightness_params():
    """
    Validate async display brightness params and empty body.

    Ensures parameters are passed through query string.
    """
    seen = {}

    async def responder(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["content"] = request.content
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = await client.set_display_brightness(front="auto", back=25)
    assert resp.result == "OK"
    assert seen["params"] == {"front": "auto", "back": "25"}
    assert seen["content"] == b""
    await client.aclose()
