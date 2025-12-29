import json

import httpx
import pytest

from busylib import AsyncBusyBar, exceptions, types


def make_client(async_responder, **kwargs) -> AsyncBusyBar:
    # MockTransport supports async responders without extra kwargs.
    transport = httpx.MockTransport(async_responder)
    return AsyncBusyBar(addr="http://device.local", transport=transport, **kwargs)


@pytest.mark.asyncio
async def test_get_version_success_async():
    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(200, json={"api_semver": "2.0.0", "branch": "dev"})

    client = make_client(responder, api_version="2.0.0")
    result = await client.get_version()
    assert isinstance(result, types.VersionInfo)
    assert result.api_semver == "2.0.0"
    await client.aclose()


@pytest.mark.asyncio
async def test_async_retry_on_transport_error():
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
    async def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request", "code": 400})

    client = make_client(responder)
    with pytest.raises(exceptions.BusyBarAPIError):
        await client.get_status()
    await client.aclose()


@pytest.mark.asyncio
async def test_async_set_display_brightness_params():
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
