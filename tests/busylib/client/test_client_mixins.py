from __future__ import annotations

import base64

import httpx
import pytest

from busylib import AsyncBusyBar, BusyBar
from busylib import display
from busylib.client import assets as assets_client
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
    resp = client.assets_upload("app", "file.bin", b"data")
    assert resp.result == "OK"
    assert seen["path"] == "/api/assets/upload"
    assert seen["params"] == {"application_name": "app", "file": "file.bin"}
    assert seen["body"] == b"data"

    resp = client.assets_delete("app")
    assert resp.result == "OK"


def test_assets_upload_sync_uses_extended_timeout_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure sync asset upload passes the mixin default upload timeout.
    """
    client = _make_sync_client(
        lambda _request: httpx.Response(200, json={"result": "OK"})
    )
    captured: dict[str, object] = {}

    def fake_request(*_args, **kwargs):
        """
        Capture timeout argument passed to the low-level request.
        """
        captured["timeout"] = kwargs.get("timeout")
        return {"result": "OK"}

    monkeypatch.setattr(client, "_request", fake_request)
    resp = client.assets_upload("app", "file.bin", b"data")
    assert resp.result == "OK"
    assert captured["timeout"] == assets_client.ASSET_UPLOAD_TIMEOUT


def test_assets_upload_sync_allows_timeout_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure sync asset upload accepts an explicit timeout override.
    """
    client = _make_sync_client(
        lambda _request: httpx.Response(200, json={"result": "OK"})
    )
    captured: dict[str, object] = {}

    def fake_request(*_args, **kwargs):
        """
        Capture timeout argument passed to the low-level request.
        """
        captured["timeout"] = kwargs.get("timeout")
        return {"result": "OK"}

    monkeypatch.setattr(client, "_request", fake_request)
    resp = client.assets_upload("app", "file.bin", b"data", timeout=7.5)
    assert resp.result == "OK"
    assert captured["timeout"] == 7.5


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
    resp = await client.assets_upload("app", "file.bin", b"data")
    assert resp.result == "OK"
    assert seen[0]["path"] == "/api/assets/upload"
    assert seen[0]["params"] == {"application_name": "app", "file": "file.bin"}
    assert seen[0]["body"] == b"data"

    resp = await client.assets_delete("app")
    assert resp.result == "OK"
    await client.aclose()


@pytest.mark.asyncio
async def test_assets_upload_async_uses_extended_timeout_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure async asset upload passes the mixin default upload timeout.
    """
    client = _make_async_client(
        lambda _request: httpx.Response(200, json={"result": "OK"})
    )
    captured: dict[str, object] = {}

    async def fake_request(*_args, **kwargs):
        """
        Capture timeout argument passed to the low-level async request.
        """
        captured["timeout"] = kwargs.get("timeout")
        return {"result": "OK"}

    monkeypatch.setattr(client, "_request", fake_request)
    resp = await client.assets_upload("app", "file.bin", b"data")
    assert resp.result == "OK"
    assert captured["timeout"] == assets_client.ASSET_UPLOAD_TIMEOUT
    await client.aclose()


@pytest.mark.asyncio
async def test_assets_upload_async_allows_timeout_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure async asset upload accepts an explicit timeout override.
    """
    client = _make_async_client(
        lambda _request: httpx.Response(200, json={"result": "OK"})
    )
    captured: dict[str, object] = {}

    async def fake_request(*_args, **kwargs):
        """
        Capture timeout argument passed to the low-level async request.
        """
        captured["timeout"] = kwargs.get("timeout")
        return {"result": "OK"}

    monkeypatch.setattr(client, "_request", fake_request)
    resp = await client.assets_upload("app", "file.bin", b"data", timeout=9.5)
    assert resp.result == "OK"
    assert captured["timeout"] == 9.5
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
    status = client.wifi_status()
    assert status.ssid == "Test"
    networks = client.wifi_networks()
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
    info = client.access()
    assert info.mode == "key"
    assert info.key_valid is True
    resp = client.access_set("enabled", "1234")
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
    snapshot = client.busy_snapshot()
    assert snapshot.snapshot.type == "SIMPLE"
    assert snapshot.snapshot.card_id == "card"
    assert snapshot.snapshot.time_left_ms == 9000
    assert snapshot.snapshot.is_paused is False
    resp = client.busy_snapshot_set(snapshot)
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
    status = await client.wifi_status()
    assert status.ssid == "Test"
    networks = await client.wifi_networks()
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
    info = await client.access()
    assert info.mode == "key"
    assert info.key_valid is True
    resp = await client.access_set("enabled", "1234")
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
    snapshot = await client.busy_snapshot()
    assert snapshot.snapshot.type == "SIMPLE"
    assert snapshot.snapshot.card_id == "card"
    assert snapshot.snapshot.time_left_ms == 9000
    assert snapshot.snapshot.is_paused is False
    resp = await client.busy_snapshot_set(snapshot)
    assert resp.result == "OK"
    assert len(seen) == 2
    assert seen[0]["path"] == "/api/busy/snapshot"
    assert seen[1]["path"] == "/api/busy/snapshot"
    await client.aclose()


def test_updater_update_sync() -> None:
    """
    Ensure firmware update sends raw body without params.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["body"] = request.content
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.update(b"fw")
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
    resp = client.time_timestamp("2025-10-02T14:30:45+04:00")
    assert resp.result == "OK"
    resp = client.time_timezone("Europe/Moscow")
    assert resp.result == "OK"
    assert seen == [
        {
            "path": "/api/time/timestamp",
            "params": {"timestamp": "2025-10-02T14:30:45+04:00"},
        },
        {"path": "/api/time/timezone", "params": {"timezone": "Europe/Moscow"}},
    ]


@pytest.mark.asyncio
async def test_updater_update_async() -> None:
    """
    Ensure async firmware update omits params.
    """

    async def responder(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {}
        assert request.content == b"fw"
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.update(b"fw")
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
    resp = await client.time_timestamp("2025-10-02T14:30:45+04:00")
    assert resp.result == "OK"
    resp = await client.time_timezone("Europe/Moscow")
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
    resp = client.update_check()
    assert resp.result == "OK"
    status = client.update_status()
    assert status.install is not None
    changelog = client.update_changelog("1.2.3")
    assert changelog.changelog == "Fixes"
    resp = client.update_install("1.2.3")
    assert resp.result == "OK"
    resp = client.update_abort_download()
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
    resp = await client.update_check()
    assert resp.result == "OK"
    status = await client.update_status()
    assert status.check is not None
    changelog = await client.update_changelog("2.0.0")
    assert changelog.changelog == "New"
    resp = await client.update_install("2.0.0")
    assert resp.result == "OK"
    resp = await client.update_abort_download()
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
    Decode the base64-encoded, L4-packed back-display HTTP response.
    """
    spec = display_client.display.get_display_spec(1)
    nibble_len = (spec.width * spec.height) // 2
    raw = bytes([0x21]) * nibble_len
    decoded = display_client._decode_frame_bytes(base64.b64encode(raw), 1)
    assert decoded is not None
    assert len(decoded) == spec.width * spec.height * 3
    assert decoded[:3] == bytes([17, 17, 17])
    assert decoded[3:6] == bytes([34, 34, 34])


def test_decode_frame_bytes_front_rgb888() -> None:
    """
    Decode the base64-encoded, uncompressed front-display HTTP response.

    `/api/screen` never compresses data (unlike the protobuf `Frame` state
    updates); the body is plain base64-encoded RGB888 bytes.
    """
    spec = display_client.display.get_display_spec(0)
    raw = bytes([1, 2, 3]) * (spec.width * spec.height)

    decoded = display_client._decode_frame_bytes(base64.b64encode(raw), 0)

    assert decoded == raw


def test_decode_frame_bytes_rejects_wrong_size() -> None:
    """
    Reject a decoded payload whose size doesn't match the display.
    """
    decoded = display_client._decode_frame_bytes(base64.b64encode(b"\x01\x02\x03"), 0)
    assert decoded is None


def test_decode_frame_bytes_rejects_invalid_base64() -> None:
    """
    Reject a payload that isn't valid base64 instead of raising.
    """
    decoded = display_client._decode_frame_bytes(b"not-base64!!", 0)
    assert decoded is None


def test_rle_decode_repeats_and_copy() -> None:
    """
    Ensure RLE decoder handles repeat and copy blocks.
    """
    repeated = display.rle_decode(bytes([2, 9, 9, 9]), 3)
    assert repeated == bytes([9, 9, 9, 9, 9, 9])

    copied = display.rle_decode(bytes([0x82, 1, 2, 3, 4, 5, 6]), 3)
    assert copied == bytes([1, 2, 3, 4, 5, 6])


def test_decode_frame_data_plain_rgb888() -> None:
    """
    RGB888/PLAIN frame data passes through unchanged.
    """
    data = bytes([10, 20, 30, 40, 50, 60])
    decoded = display.decode_frame_data("PLAIN", "RGB888", data)
    assert decoded == data


def test_decode_frame_data_plain_l8() -> None:
    """
    L8/PLAIN grayscale bytes expand to RGB triplets without scaling.
    """
    decoded = display.decode_frame_data("PLAIN", "L8", bytes([5, 250]))
    assert decoded == bytes([5, 5, 5, 250, 250, 250])


def test_decode_frame_data_plain_l4() -> None:
    """
    L4/PLAIN packed nibbles unpack and scale into RGB triplets.
    """
    decoded = display.decode_frame_data("PLAIN", "L4", bytes([0x21]))
    assert decoded == bytes([17, 17, 17, 34, 34, 34])


def test_decode_frame_data_run_length_rgb888() -> None:
    """
    RUN_LENGTH-encoded RGB888 frame data decodes via the RLE repeat block.
    """
    rle = bytes([2, 1, 2, 3])  # repeat (1,2,3) twice
    decoded = display.decode_frame_data("RUN_LENGTH", "RGB888", rle)
    assert decoded == bytes([1, 2, 3, 1, 2, 3])


def test_decode_frame_data_deflate_rgb888() -> None:
    """
    DEFLATE-encoded RGB888 frame data inflates before use.
    """
    import zlib

    raw = bytes([9, 8, 7, 6, 5, 4])
    decoded = display.decode_frame_data("DEFLATE", "RGB888", zlib.compress(raw))
    assert decoded == raw


def test_decode_frame_data_deflate_run_length_l8() -> None:
    """
    DEFLATE_RUN_LENGTH first inflates, then RLE-decodes the result.
    """
    import zlib

    rle = bytes([3, 42])  # repeat single L8 byte 3 times
    decoded = display.decode_frame_data(
        "DEFLATE_RUN_LENGTH", "L8", zlib.compress(rle)
    )
    assert decoded == bytes([42, 42, 42] * 3)


def test_decode_frame_data_unsupported_pixel_format() -> None:
    """
    Unknown pixel formats raise instead of silently misrendering.
    """
    with pytest.raises(ValueError, match="pixel_format"):
        display.decode_frame_data("PLAIN", "YUV420", b"\x00")


def test_decode_frame_data_unsupported_encoding() -> None:
    """
    Unknown encodings raise instead of silently misrendering.
    """
    with pytest.raises(ValueError, match="encoding"):
        display.decode_frame_data("LZMA", "RGB888", b"\x00")
