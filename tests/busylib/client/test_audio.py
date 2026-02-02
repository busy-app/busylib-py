from __future__ import annotations

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
        seen.append(
            {
                "path": request.url.path,
                "method": request.method,
                "params": dict(request.url.params),
            }
        )
        if request.url.path == "/api/audio/volume" and request.method == "GET":
            return httpx.Response(200, json={"volume": 42.0})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.play_audio("app", "/ext/app.wav")
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
            "params": {"app_id": "app", "path": "/ext/app.wav"},
        },
        {"path": "/api/audio/play", "method": "DELETE", "params": {}},
        {"path": "/api/audio/play", "method": "DELETE", "params": {}},
        {"path": "/api/audio/volume", "method": "GET", "params": {}},
        {"path": "/api/audio/volume", "method": "POST", "params": {"volume": "55.5"}},
    ]


@pytest.mark.asyncio
async def test_audio_play_stop_volume_async() -> None:
    """
    Validate audio playback and volume endpoints for async client.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "method": request.method,
                "params": dict(request.url.params),
            }
        )
        if request.url.path == "/api/audio/volume" and request.method == "GET":
            return httpx.Response(200, json={"volume": 17.0})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.play_audio("app", "/ext/app.wav")
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
            "params": {"app_id": "app", "path": "/ext/app.wav"},
        },
        {"path": "/api/audio/play", "method": "DELETE", "params": {}},
        {"path": "/api/audio/play", "method": "DELETE", "params": {}},
        {"path": "/api/audio/volume", "method": "GET", "params": {}},
        {"path": "/api/audio/volume", "method": "POST", "params": {"volume": "12.5"}},
    ]
