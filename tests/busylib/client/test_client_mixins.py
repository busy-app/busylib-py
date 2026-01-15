from __future__ import annotations

import httpx
import pytest

from busylib import AsyncBusyBar, BusyBar
from busylib.client import display as display_client


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


def test_assets_upload_and_delete_sync() -> None:
    """
    Validate asset upload and deletion endpoints with params and body.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["body"] = request.content
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.upload_asset("app", "file.bin", b"data")
    assert resp.result == "OK"
    assert seen["path"] == "/api/assets/upload"
    assert seen["params"] == {"app_id": "app", "file": "file.bin"}
    assert seen["body"] == b"data"

    resp = client.delete_app_assets("app")
    assert resp.result == "OK"


@pytest.mark.asyncio
async def test_assets_upload_and_delete_async() -> None:
    """
    Validate async asset upload and deletion endpoints with params and body.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "params": dict(request.url.params),
                "body": request.content,
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.upload_asset("app", "file.bin", b"data")
    assert resp.result == "OK"
    assert seen[0]["path"] == "/api/assets/upload"
    assert seen[0]["params"] == {"app_id": "app", "file": "file.bin"}
    assert seen[0]["body"] == b"data"

    resp = await client.delete_app_assets("app")
    assert resp.result == "OK"
    await client.aclose()


def test_ble_and_wifi_status_sync() -> None:
    """
    Ensure BLE and Wi-Fi status endpoints parse into models.
    """
    seen: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/ble/status":
            return httpx.Response(200, json={"state": "on"})
        if request.url.path == "/api/wifi/status":
            return httpx.Response(200, json={"state": "connected", "ssid": "Test"})
        if request.url.path == "/api/wifi/networks":
            return httpx.Response(200, json={"count": 0, "networks": []})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    ble = client.ble_status()
    assert ble.state == "on"
    status = client.get_wifi_status()
    assert status.ssid == "Test"
    networks = client.scan_wifi_networks()
    assert networks.count == 0
    assert seen == ["/api/ble/status", "/api/wifi/status", "/api/wifi/networks"]


@pytest.mark.asyncio
async def test_ble_and_wifi_status_async() -> None:
    """
    Ensure async BLE and Wi-Fi status endpoints parse into models.
    """
    seen: list[str] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/ble/status":
            return httpx.Response(200, json={"state": "on"})
        if request.url.path == "/api/wifi/status":
            return httpx.Response(200, json={"state": "connected", "ssid": "Test"})
        if request.url.path == "/api/wifi/networks":
            return httpx.Response(200, json={"count": 0, "networks": []})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    ble = await client.ble_status()
    assert ble.state == "on"
    status = await client.get_wifi_status()
    assert status.ssid == "Test"
    networks = await client.scan_wifi_networks()
    assert networks.count == 0
    assert seen == ["/api/ble/status", "/api/wifi/status", "/api/wifi/networks"]
    await client.aclose()


def test_firmware_update_sync_params() -> None:
    """
    Ensure firmware update uses optional name param and raw body.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["body"] = request.content
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.update_firmware(b"fw", name="demo.bin")
    assert resp.result == "OK"
    assert seen["params"] == {"name": "demo.bin"}
    assert seen["body"] == b"fw"


@pytest.mark.asyncio
async def test_firmware_update_async_no_name() -> None:
    """
    Ensure async firmware update omits params when name is absent.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {}
        assert request.content == b"fw"
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.update_firmware(b"fw")
    assert resp.result == "OK"
    await client.aclose()


def test_decode_frame_bytes_back_nibbles() -> None:
    """
    Decode back display nibble data into grayscale RGB bytes.
    """
    spec = display_client.display.get_display_spec(1)
    nibble_len = (spec.width * spec.height) // 2
    data = bytes([0x21]) * nibble_len
    decoded = display_client._decode_frame_bytes(data, 1, from_ws=False)
    assert decoded is not None
    assert len(decoded) == spec.width * spec.height * 3
    assert decoded[:3] == bytes([17, 17, 17])
    assert decoded[3:6] == bytes([34, 34, 34])


def test_rle_decode_repeats_and_copy() -> None:
    """
    Ensure RLE decoder handles repeat and copy blocks.
    """
    repeated = display_client._rle_decode(bytes([2, 9, 9, 9]), 3)
    assert repeated == bytes([9, 9, 9, 9, 9, 9])

    copied = display_client._rle_decode(bytes([0x82, 1, 2, 3, 4, 5, 6]), 3)
    assert copied == bytes([1, 2, 3, 4, 5, 6])
