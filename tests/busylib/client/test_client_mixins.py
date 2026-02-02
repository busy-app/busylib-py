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


def test_access_mode_sync() -> None:
    """
    Ensure HTTP access endpoints use query params and parse info.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "params": dict(request.url.params)})
        if request.url.path == "/api/access":
            if request.method == "GET":
                return httpx.Response(200, json={"mode": "key", "key_valid": True})
            return httpx.Response(200, json={"result": "OK"})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    info = client.get_http_access()
    assert info.mode == "key"
    assert info.key_valid is True
    resp = client.set_http_access("enabled", "1234")
    assert resp.result == "OK"
    assert seen == [
        {"path": "/api/access", "params": {}},
        {"path": "/api/access", "params": {"mode": "enabled", "key": "1234"}},
    ]


def test_busy_snapshot_sync() -> None:
    """
    Ensure busy snapshot endpoints send and parse payloads.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "body": request.content})
        if request.url.path == "/api/busy/snapshot":
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "snapshot": {
                            "type": "SIMPLE",
                            "card_id": "card",
                            "time_left_ms": 9000,
                            "is_paused": False,
                        },
                        "snapshot_timestamp_ms": 123,
                    },
                )
            return httpx.Response(200, json={"result": "OK"})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    snapshot = client.get_busy_snapshot()
    assert snapshot.snapshot.type == "SIMPLE"
    assert snapshot.snapshot.card_id == "card"
    assert snapshot.snapshot.time_left_ms == 9000
    assert snapshot.snapshot.is_paused is False
    resp = client.set_busy_snapshot(snapshot)
    assert resp.result == "OK"
    assert len(seen) == 2
    assert seen[0]["path"] == "/api/busy/snapshot"
    assert seen[1]["path"] == "/api/busy/snapshot"


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


@pytest.mark.asyncio
async def test_access_mode_async() -> None:
    """
    Ensure async HTTP access endpoints use query params and parse info.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "params": dict(request.url.params)})
        if request.url.path == "/api/access":
            if request.method == "GET":
                return httpx.Response(200, json={"mode": "key", "key_valid": True})
            return httpx.Response(200, json={"result": "OK"})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    info = await client.get_http_access()
    assert info.mode == "key"
    assert info.key_valid is True
    resp = await client.set_http_access("enabled", "1234")
    assert resp.result == "OK"
    assert seen == [
        {"path": "/api/access", "params": {}},
        {"path": "/api/access", "params": {"mode": "enabled", "key": "1234"}},
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_busy_snapshot_async() -> None:
    """
    Ensure async busy snapshot endpoints send and parse payloads.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "body": request.content})
        if request.url.path == "/api/busy/snapshot":
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "snapshot": {
                            "type": "SIMPLE",
                            "card_id": "card",
                            "time_left_ms": 9000,
                            "is_paused": False,
                        },
                        "snapshot_timestamp_ms": 123,
                    },
                )
            return httpx.Response(200, json={"result": "OK"})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    snapshot = await client.get_busy_snapshot()
    assert snapshot.snapshot.type == "SIMPLE"
    assert snapshot.snapshot.card_id == "card"
    assert snapshot.snapshot.time_left_ms == 9000
    assert snapshot.snapshot.is_paused is False
    resp = await client.set_busy_snapshot(snapshot)
    assert resp.result == "OK"
    assert len(seen) == 2
    assert seen[0]["path"] == "/api/busy/snapshot"
    assert seen[1]["path"] == "/api/busy/snapshot"
    await client.aclose()


def test_updater_update_firmware_sync() -> None:
    """
    Ensure firmware update sends raw body without params.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["body"] = request.content
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.update_firmware(b"fw")
    assert resp.result == "OK"
    assert seen["params"] == {}
    assert seen["body"] == b"fw"


def test_time_endpoints_sync() -> None:
    """
    Ensure time endpoints use query params.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "params": dict(request.url.params)})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.set_time_timestamp("2025-10-02T14:30:45+04:00")
    assert resp.result == "OK"
    resp = client.set_time_timezone("Europe/Moscow")
    assert resp.result == "OK"
    assert seen == [
        {
            "path": "/api/time/timestamp",
            "params": {"timestamp": "2025-10-02T14:30:45+04:00"},
        },
        {"path": "/api/time/timezone", "params": {"timezone": "Europe/Moscow"}},
    ]


@pytest.mark.asyncio
async def test_updater_update_firmware_async() -> None:
    """
    Ensure async firmware update omits params.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {}
        assert request.content == b"fw"
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.update_firmware(b"fw")
    assert resp.result == "OK"
    await client.aclose()


@pytest.mark.asyncio
async def test_time_endpoints_async() -> None:
    """
    Ensure async time endpoints use query params.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "params": dict(request.url.params)})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.set_time_timestamp("2025-10-02T14:30:45+04:00")
    assert resp.result == "OK"
    resp = await client.set_time_timezone("Europe/Moscow")
    assert resp.result == "OK"
    assert seen == [
        {
            "path": "/api/time/timestamp",
            "params": {"timestamp": "2025-10-02T14:30:45+04:00"},
        },
        {"path": "/api/time/timezone", "params": {"timezone": "Europe/Moscow"}},
    ]
    await client.aclose()


def test_updater_check_status_and_changelog_sync() -> None:
    """
    Ensure updater endpoints call correct paths and params.
    """
    seen: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/update/status":
            return httpx.Response(200, json={"install": {"status": "ok"}})
        if request.url.path == "/api/update/changelog":
            assert dict(request.url.params) == {"version": "1.2.3"}
            return httpx.Response(200, json={"changelog": "Fixes"})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.check_firmware_update()
    assert resp.result == "OK"
    status = client.get_update_status()
    assert status.install is not None
    changelog = client.get_update_changelog("1.2.3")
    assert changelog.changelog == "Fixes"
    resp = client.install_firmware_update("1.2.3")
    assert resp.result == "OK"
    resp = client.abort_firmware_download()
    assert resp.result == "OK"
    assert seen == [
        "/api/update/check",
        "/api/update/status",
        "/api/update/changelog",
        "/api/update/install",
        "/api/update/abort_download",
    ]


@pytest.mark.asyncio
async def test_updater_check_status_and_changelog_async() -> None:
    """
    Ensure async updater endpoints call correct paths and params.
    """
    seen: list[str] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/update/status":
            return httpx.Response(200, json={"check": {"result": "available"}})
        if request.url.path == "/api/update/changelog":
            assert dict(request.url.params) == {"version": "2.0.0"}
            return httpx.Response(200, json={"changelog": "New"})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.check_firmware_update()
    assert resp.result == "OK"
    status = await client.get_update_status()
    assert status.check is not None
    changelog = await client.get_update_changelog("2.0.0")
    assert changelog.changelog == "New"
    resp = await client.install_firmware_update("2.0.0")
    assert resp.result == "OK"
    resp = await client.abort_firmware_download()
    assert resp.result == "OK"
    assert seen == [
        "/api/update/check",
        "/api/update/status",
        "/api/update/changelog",
        "/api/update/install",
        "/api/update/abort_download",
    ]
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
