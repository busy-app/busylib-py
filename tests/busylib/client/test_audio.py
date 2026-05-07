from __future__ import annotations

import json

import httpx
import pytest
from busylib import AsyncBusyBar, BusyBar, types
from busylib import exceptions


def _make_sync_client(responder) -> BusyBar:
    """
    Build a BusyBar client with a mock transport responder.
    """
    transport = httpx.MockTransport(responder)
    return BusyBar(addr="http://device.local", transport=transport)


def _make_async_client(responder) -> AsyncBusyBar:
    """
    Build an AsyncBusyBar client with a mock transport responder.
    """
    transport = httpx.MockTransport(responder)
    return AsyncBusyBar(addr="http://device.local", transport=transport)


def test_audio_play_stop_volume_sync() -> None:
    """
    Validate audio play, stop, and volume endpoints for sync client.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "method": request.method,
                "params": dict(request.url.params),
                "body": json.loads(request.content) if request.content else None,
            }
        )
        if request.url.path == "/api/audio/volume" and request.method == "GET":
            return httpx.Response(200, json={"volume": 42.0})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.audio_play(application_name="app", path="/ext/app.wav")
    assert resp.result == "OK"
    resp = client.audio_stop()
    assert resp.result == "OK"
    resp = client.audio_stop()
    assert resp.result == "OK"
    info = client.audio_volume()
    assert isinstance(info, types.AudioVolumeInfo)
    assert info.volume == 42.0
    resp = client.audio_volume_set(55.5)
    assert resp.result == "OK"

    assert seen == [
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {},
            "body": {"application_name": "app", "path": "/ext/app.wav"},
        },
        {"path": "/api/audio/play", "method": "DELETE", "params": {}, "body": None},
        {"path": "/api/audio/play", "method": "DELETE", "params": {}, "body": None},
        {"path": "/api/audio/volume", "method": "GET", "params": {}, "body": None},
        {
            "path": "/api/audio/volume",
            "method": "POST",
            "params": {"volume": "55.5"},
            "body": None,
        },
    ]


def test_audio_play_sync_supports_session_header() -> None:
    """
    Ensure audio_play forwards x-session-id through request kwargs.
    """
    seen: dict[str, str] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["session"] = request.headers.get("x-session-id", "")
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.audio_play(
        application_name="app",
        path="/ext/app.wav",
        session_id="bar-1",
    )
    assert resp.result == "OK"
    assert seen["session"] == "bar-1"


def test_audio_play_sync_supports_stock_path_payload() -> None:
    """
    Send stock-path playback payload without application context in payload.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.audio_play(payload={"stock_path": "shared/sfx.snd"})
    assert resp.result == "OK"
    assert seen == {"stock_path": "shared/sfx.snd"}


def test_audio_play_sync_rejects_payload_application_name() -> None:
    """
    Reject application_name inside audio payload; request context owns it.
    """
    client = _make_sync_client(
        lambda _request: httpx.Response(200, json={"result": "OK"})
    )
    with pytest.raises(exceptions.BusyBarResponseValidationError):
        client.audio_play(
            application_name="app",
            payload={
                "application_name": "legacy",
                "stock_path": "shared/sfx.snd",
            },
        )


def test_audio_play_sync_keyword_arguments_override_payload() -> None:
    """
    Let explicit path and stock_path keyword arguments override payload keys.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.audio_play(
        payload={"path": "old.wav"},
        stock_path="shared/sfx.snd",
    )
    assert resp.result == "OK"
    assert seen == {"stock_path": "shared/sfx.snd"}


@pytest.mark.asyncio
async def test_audio_play_stop_volume_async() -> None:
    """
    Validate audio play, stop, and volume endpoints for async client.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "method": request.method,
                "params": dict(request.url.params),
                "body": json.loads(request.content) if request.content else None,
            }
        )
        if request.url.path == "/api/audio/volume" and request.method == "GET":
            return httpx.Response(200, json={"volume": 17.0})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.audio_play(application_name="app", path="/ext/app.wav")
    assert resp.result == "OK"
    resp = await client.audio_stop()
    assert resp.result == "OK"
    resp = await client.audio_stop()
    assert resp.result == "OK"
    info = await client.audio_volume()
    assert isinstance(info, types.AudioVolumeInfo)
    assert info.volume == 17.0
    resp = await client.audio_volume_set(12.5)
    assert resp.result == "OK"
    await client.aclose()

    assert seen == [
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {},
            "body": {"application_name": "app", "path": "/ext/app.wav"},
        },
        {"path": "/api/audio/play", "method": "DELETE", "params": {}, "body": None},
        {"path": "/api/audio/play", "method": "DELETE", "params": {}, "body": None},
        {"path": "/api/audio/volume", "method": "GET", "params": {}, "body": None},
        {
            "path": "/api/audio/volume",
            "method": "POST",
            "params": {"volume": "12.5"},
            "body": None,
        },
    ]


@pytest.mark.asyncio
async def test_audio_play_async_supports_session_header() -> None:
    """
    Ensure async audio_play forwards x-session-id through request kwargs.
    """
    seen: dict[str, str] = {}

    async def responder(request: httpx.Request) -> httpx.Response:
        seen["session"] = request.headers.get("x-session-id", "")
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.audio_play(
        application_name="app",
        path="/ext/app.wav",
        session_id="bar-2",
    )
    assert resp.result == "OK"
    assert seen["session"] == "bar-2"
    await client.aclose()


@pytest.mark.asyncio
async def test_audio_play_async_supports_stock_path_payload() -> None:
    """
    Send stock-path playback payload in async mode.
    """
    seen: dict[str, object] = {}

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.audio_play(payload={"stock_path": "shared/sfx.snd"})
    assert resp.result == "OK"
    assert seen == {"stock_path": "shared/sfx.snd"}
    await client.aclose()
