import json

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
async def test_version_success_async():
    """
    Parse version information from the async client.

    Ensures the response is mapped to VersionInfo.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(200, json={"api_semver": "2.0.0", "branch": "dev"})

    client = make_client(responder, api_version="2.0.0")
    result = await client.version()
    assert isinstance(result, types.VersionInfo)
    assert result.api_semver == "2.0.0"
    await client.aclose()


@pytest.mark.asyncio
async def test_name_and_time_async():
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
    name = await client.name()
    assert name.name == "BusyBar"
    time_info = await client.time()
    assert time_info.timestamp == "2024-01-01T10:00:00"
    await client.aclose()


@pytest.mark.asyncio
async def test_name_set_async() -> None:
    """
    Send device name update payload via async POST /api/name.
    """
    seen: dict[str, object] = {}

    async def responder(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = await client.name_set("Busy Desk")
    assert resp.result == "OK"
    assert seen["path"] == "/api/name"
    assert seen["method"] == "POST"
    assert seen["body"] == {"name": "Busy Desk"}
    await client.aclose()


@pytest.mark.asyncio
async def test_name_set_async_rejects_empty() -> None:
    """
    Reject empty device names before async request send.
    """
    client = make_client(lambda _request: httpx.Response(200, json={"result": "OK"}))
    with pytest.raises(ValueError):
        await client.name_set("")
    await client.aclose()


@pytest.mark.asyncio
async def test_account_info_async():
    """
    Parse linked account info from the async client.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/info"
        return httpx.Response(200, json={"linked": False, "email": "name@example.com"})

    client = make_client(responder)
    result = await client.account_info()
    assert result.linked is False
    assert result.email == "name@example.com"
    await client.aclose()


@pytest.mark.asyncio
async def test_account_status_async():
    """
    Parse MQTT account state from the async client.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/status"
        return httpx.Response(200, json={"state": "connected"})

    client = make_client(responder)
    result = await client.account_status()
    assert result.state == "connected"
    await client.aclose()


@pytest.mark.asyncio
async def test_account_link_async():
    """
    Parse account link response from the async client.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/link"
        return httpx.Response(200, json={"code": "EFGH", "expires_at": 1700000001})

    client = make_client(responder)
    result = await client.account_link()
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
    resp = await client.wifi_enable()
    assert resp.result == "OK"
    assert calls["count"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_display_draw_utf8_async():
    """
    Ensure async display payloads preserve UTF-8 content.

    Verifies non-ASCII text is not escaped.
    """
    payload = {
        "application_name": "demo",
        "elements": [
            {
                "id": "1",
                "type": "text",
                "x": 0,
                "y": 0,
                "text": "Café",
                "font": "small",
                "display": "front",
            }
        ],
    }

    async def responder(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert "Café" in body
        assert "\\u00e9" not in body
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = await client.display_draw(payload)
    assert resp.result == "OK"
    await client.aclose()


@pytest.mark.asyncio
async def test_display_draw_and_clear_params_async() -> None:
    """
    Validate async display_draw and display_clear session header.
    """

    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "method": request.method,
                "params": dict(request.url.params),
                "session": request.headers.get("x-session-id"),
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    payload = {
        "application_name": "demo",
        "elements": [
            {"id": "1", "type": "text", "x": 0, "y": 0, "text": "A", "font": "small"}
        ],
    }
    draw_resp = await client.display_draw(payload, session_id="bar-2")
    clear_resp = await client.display_clear(
        application_name="demo",
        session_id="bar-2",
    )
    assert draw_resp.result == "OK"
    assert clear_resp.result == "OK"
    assert seen[0]["path"] == "/api/display/draw"
    assert seen[0]["method"] == "POST"
    assert seen[0]["session"] == "bar-2"
    assert seen[1]["path"] == "/api/display/draw"
    assert seen[1]["method"] == "DELETE"
    assert seen[1]["params"] == {"application_name": "demo"}
    assert seen[1]["session"] == "bar-2"
    await client.aclose()


@pytest.mark.asyncio
async def test_display_draw_can_clear_before_draw_async() -> None:
    """
    Validate async clear_before_draw in display_draw.
    """

    seen: list[tuple[str, str, dict[str, str]]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    payload = {
        "application_name": "demo",
        "elements": [
            {"id": "1", "type": "text", "x": 0, "y": 0, "text": "A", "font": "small"}
        ],
    }
    resp = await client.display_draw(payload, clear_before_draw=True)
    assert resp.result == "OK"
    assert seen[0] == (
        "DELETE",
        "/api/display/draw",
        {"application_name": "demo"},
    )
    assert seen[1][0] == "POST"
    await client.aclose()


@pytest.mark.asyncio
async def test_display_can_clear_draw_and_audio_play_async() -> None:
    """
    Validate async high-level display flow: clear, draw, and audio_play.
    """

    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "body": json.loads(request.content) if request.content else None,
                "session": request.headers.get("x-session-id"),
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    payload = {
        "application_name": "demo",
        "elements": [
            {"id": "1", "type": "text", "x": 0, "y": 0, "text": "A", "font": "small"}
        ],
    }
    normalized_payload = {
        "application_name": "demo",
        "priority": 50,
        "elements": [
            {
                "id": "1",
                "display": "front",
                "type": "text",
                "x": 0,
                "y": 0,
                "text": "A",
                "font": "small",
            }
        ],
    }
    resp = await client.display(
        payload,
        session_id="bar-2",
        clear_before_draw=True,
        audio_payload={"stock_path": "shared/sfx.snd"},
    )
    assert resp.result == "OK"
    assert seen == [
        {
            "method": "DELETE",
            "path": "/api/display/draw",
            "params": {"application_name": "demo"},
            "body": None,
            "session": "bar-2",
        },
        {
            "method": "POST",
            "path": "/api/display/draw",
            "params": {},
            "body": normalized_payload,
            "session": "bar-2",
        },
        {
            "method": "POST",
            "path": "/api/audio/play",
            "params": {},
            "body": {"stock_path": "shared/sfx.snd"},
            "session": "bar-2",
        },
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_display_draw_can_sanitize_text_payload_async(caplog) -> None:
    """
    Validate sanitize_text for async display_draw.
    """

    seen: dict[str, str] = {}

    async def responder(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    caplog.set_level("WARNING", logger="busylib.client.display")
    payload = {
        "application_name": "demo",
        "elements": [
            {
                "id": "1",
                "type": "text",
                "x": 0,
                "y": 0,
                "text": "Demo 🚀\nmeeting",
                "display": "front",
                "font": "small",
            }
        ],
    }
    resp = await client.display_draw(payload, sanitize_text=True)
    assert resp.result == "OK"
    assert "Demo meeting" in seen["body"]
    assert "🚀" not in seen["body"]
    assert (
        "Sanitized display text element_id=1 display=front "
        "text_before='Demo 🚀\\nmeeting' text_after='Demo meeting'"
    ) in caplog.text
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
        await client.status()
    await client.aclose()


@pytest.mark.asyncio
async def test_async_display_brightness_set_params():
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
    resp = await client.display_brightness_set("auto")
    assert resp.result == "OK"
    assert seen["params"] == {"value": "auto"}
    assert seen["content"] == b""
    await client.aclose()
