from __future__ import annotations

import json

import httpx
import pytest

from busylib import AsyncBusyBar, BusyBar, types


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
    Validate audio playback and volume endpoints for sync client.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        seen.append(
            {
                "path": request.url.path,
                "method": request.method,
                "params": dict(request.url.params),
                "json": json.loads(body) if body else None,
            }
        )
        if request.url.path == "/api/audio/volume" and request.method == "GET":
            return httpx.Response(200, json={"volume": 42.0})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.play_audio("app", "sounds/event.snd")
    assert resp.result == "OK"
    resp = client.stop_audio()
    assert resp.result == "OK"
    resp = client.stop_sound()
    assert resp.result == "OK"
    info = client.get_audio_volume()
    assert isinstance(info, types.AudioVolumeInfo)
    assert info.volume == 42.0
    resp = client.set_audio_volume(55.5)
    assert resp.result == "OK"

    assert seen == [
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {},
            "json": {"application_name": "app", "path": "sounds/event.snd"},
        },
        {"path": "/api/audio/play", "method": "DELETE", "params": {}, "json": None},
        {"path": "/api/audio/play", "method": "DELETE", "params": {}, "json": None},
        {"path": "/api/audio/volume", "method": "GET", "params": {}, "json": None},
        {
            "path": "/api/audio/volume",
            "method": "POST",
            "params": {"volume": "55.5"},
            "json": None,
        },
    ]


@pytest.mark.asyncio
async def test_audio_play_stop_volume_async() -> None:
    """
    Validate audio playback and volume endpoints for async client.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        seen.append(
            {
                "path": request.url.path,
                "method": request.method,
                "params": dict(request.url.params),
                "json": json.loads(body) if body else None,
            }
        )
        if request.url.path == "/api/audio/volume" and request.method == "GET":
            return httpx.Response(200, json={"volume": 17.0})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.play_audio("app", "sounds/event.snd")
    assert resp.result == "OK"
    resp = await client.stop_audio()
    assert resp.result == "OK"
    resp = await client.stop_sound()
    assert resp.result == "OK"
    info = await client.get_audio_volume()
    assert isinstance(info, types.AudioVolumeInfo)
    assert info.volume == 17.0
    resp = await client.set_audio_volume(12.5)
    assert resp.result == "OK"
    await client.aclose()

    assert seen == [
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {},
            "json": {"application_name": "app", "path": "sounds/event.snd"},
        },
        {"path": "/api/audio/play", "method": "DELETE", "params": {}, "json": None},
        {"path": "/api/audio/play", "method": "DELETE", "params": {}, "json": None},
        {"path": "/api/audio/volume", "method": "GET", "params": {}, "json": None},
        {
            "path": "/api/audio/volume",
            "method": "POST",
            "params": {"volume": "12.5"},
            "json": None,
        },
    ]


def test_audio_play_stock_path_sync() -> None:
    """
    Send stock sound playback payload using shared resource reference.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "method": request.method,
                "params": dict(request.url.params),
                "json": json.loads(request.content.decode("utf-8")),
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.play_audio(stock_path="shared/Calendar_event_starts.snd")
    assert resp.result == "OK"
    assert seen == [
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {},
            "json": {"stock_path": "shared/Calendar_event_starts.snd"},
        }
    ]


def test_audio_play_legacy_fallback_sync() -> None:
    """
    Fallback to legacy query params when JSON audio play is not supported.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        item = {
            "path": request.url.path,
            "method": request.method,
            "params": dict(request.url.params),
            "json": (
                None
                if not request.content
                else json.loads(request.content.decode("utf-8"))
            ),
        }
        seen.append(item)
        if request.method == "POST" and request.url.path == "/api/audio/play":
            if item["params"]:
                return httpx.Response(200, json={"result": "OK"})
            return httpx.Response(400, json={"error": "bad request", "code": 400})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.play_audio("calendar", "sounds/reminder.snd")
    assert resp.result == "OK"
    assert seen == [
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {},
            "json": {"application_name": "calendar", "path": "sounds/reminder.snd"},
        },
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {
                "application_name": "calendar",
                "path": "sounds/reminder.snd",
            },
            "json": None,
        },
    ]


@pytest.mark.asyncio
async def test_audio_play_legacy_fallback_async() -> None:
    """
    Fallback to legacy query params in async mode when JSON is rejected.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        item = {
            "path": request.url.path,
            "method": request.method,
            "params": dict(request.url.params),
            "json": (
                None
                if not request.content
                else json.loads(request.content.decode("utf-8"))
            ),
        }
        seen.append(item)
        if request.method == "POST" and request.url.path == "/api/audio/play":
            if item["params"]:
                return httpx.Response(200, json={"result": "OK"})
            return httpx.Response(400, json={"error": "bad request", "code": 400})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.play_audio("calendar", "sounds/reminder.snd")
    assert resp.result == "OK"
    await client.aclose()
    assert seen == [
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {},
            "json": {"application_name": "calendar", "path": "sounds/reminder.snd"},
        },
        {
            "path": "/api/audio/play",
            "method": "POST",
            "params": {
                "application_name": "calendar",
                "path": "sounds/reminder.snd",
            },
            "json": None,
        },
    ]
