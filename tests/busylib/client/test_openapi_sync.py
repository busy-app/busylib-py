from __future__ import annotations

import json

import httpx
import pytest

from busylib import AsyncBusyBar, BusyBar, exceptions, types


def _make_sync_client(responder) -> BusyBar:
    """
    Build a sync client with a mock transport responder.
    """
    transport = httpx.MockTransport(responder)
    return BusyBar(addr="http://device.local", transport=transport)


def _make_async_client(responder) -> AsyncBusyBar:
    """
    Build an async client with a mock transport responder.
    """
    transport = httpx.MockTransport(responder)
    return AsyncBusyBar(addr="http://device.local", transport=transport)


def _busy_profile_payload() -> dict[str, object]:
    """
    Return a complete BusyProfile payload matching the firmware OpenAPI schema.
    """
    return {
        "sort_order": 1,
        "title": "Focus",
        "id": "00000000-0000-0000-0000-000000000000",
        "timer_settings": {"type": "SIMPLE", "total_time_ms": 300000},
        "busy_bar_settings": {
            "theme": "on_air",
            "show_work_phase_only": False,
            "trigger_smart_home": True,
        },
        "profile_timestamp_ms": 123,
    }


def test_account_backend_sync_requests_match_openapi() -> None:
    """
    Ensure account backend helpers use the documented path and JSON payload.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": request.content,
            }
        )
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "server_url": "default",
                    "client_cert_type": "default",
                    "ignore_server_cert": False,
                },
            )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    backend = client.account_backend()
    response = client.account_backend_set(
        {
            "server_url": "mqtts://mqtt.example.com:8883",
            "client_cert_type": "custom",
            "ignore_server_cert": True,
        }
    )

    assert backend.server_url == "default"
    assert response.result == "OK"
    assert seen[0] == {"method": "GET", "path": "/api/account/backend", "body": b""}
    assert seen[1]["method"] == "PUT"
    assert seen[1]["path"] == "/api/account/backend"
    account_body = seen[1]["body"]
    assert isinstance(account_body, bytes)
    assert json.loads(account_body) == {
        "server_url": "mqtts://mqtt.example.com:8883",
        "client_cert_type": "custom",
        "ignore_server_cert": True,
    }


def test_busy_profile_sync_requests_match_openapi() -> None:
    """
    Ensure busy profile helpers use slot paths and serialize profile bodies.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": request.content,
            }
        )
        if request.method == "GET":
            return httpx.Response(200, json=_busy_profile_payload())
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    profile = client.busy_profile("busy")
    response = client.busy_profile_set("custom", profile)

    assert profile.timer_settings.type == "SIMPLE"
    assert response.result == "OK"
    assert seen[0]["path"] == "/api/busy/profiles/busy"
    assert seen[1]["method"] == "PUT"
    assert seen[1]["path"] == "/api/busy/profiles/custom"
    busy_body = seen[1]["body"]
    assert isinstance(busy_body, bytes)
    assert json.loads(busy_body)["busy_bar_settings"] == {
        "theme": "on_air",
        "show_work_phase_only": False,
        "trigger_smart_home": True,
    }


def test_system_time_update_and_storage_endpoints_match_openapi() -> None:
    """
    Cover newly documented system, time, autoupdate, and storage endpoints.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "body": request.content,
            }
        )
        if request.url.path == "/api/transport":
            return httpx.Response(200, json={"type": "wifi"})
        if request.url.path == "/api/status/device":
            return httpx.Response(
                200,
                json={
                    "serial_number": "203638485431500400123456",
                    "usb_mac": "0c:fa:22:21:2a:31",
                    "otp_valid": True,
                    "firmware_security": "secure",
                },
            )
        if request.url.path == "/api/status/firmware":
            return httpx.Response(
                200,
                json={
                    "version": "1.0.0",
                    "target": 22,
                    "branch": "dev",
                    "build_date": "2026-06-19",
                    "commit_hash": "abc123",
                    "intercom_version": "intercom",
                },
            )
        if request.url.path == "/api/time/timezone" and request.method == "GET":
            return httpx.Response(
                200,
                json={"name": "Bangalore", "offset": "+05:30", "abbr": "IST"},
            )
        if request.url.path == "/api/time/tzlist":
            return httpx.Response(
                200,
                json={"list": [{"name": "UTC", "offset": "+00:00", "abbr": "UTC"}]},
            )
        if request.url.path == "/api/update/autoupdate" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "is_enabled": True,
                    "interval_start": "00:00",
                    "interval_end": "08:00",
                },
            )
        if request.url.path == "/api/log_dump":
            return httpx.Response(
                200,
                json={"result": "OK", "path": "/ext/dump.txt"},
            )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    assert client.transport().type == "wifi"
    device = client.status_device()
    assert device.serial_number == "203638485431500400123456"
    assert device.firmware_security == "secure"
    firmware = client.status_firmware()
    assert firmware.target == 22
    assert firmware.intercom_version == "intercom"
    assert client.time_timezone_info().abbr == "IST"
    assert client.time_timezone_list().list[0].name == "UTC"
    assert client.storage_rename("/ext/a.txt", "/ext/b.txt").result == "OK"
    log_dump = client.log_dump(filename="dump")
    assert log_dump.result == "OK"
    assert log_dump.path == "/ext/dump.txt"
    autoupdate = client.update_autoupdate()
    assert autoupdate.is_enabled is True
    assert client.update_autoupdate_set({"is_enabled": False}).result == "OK"

    storage_request = next(
        item for item in seen if item["path"] == "/api/storage/rename"
    )
    log_dump_request = next(item for item in seen if item["path"] == "/api/log_dump")
    autoupdate_put = next(
        item
        for item in seen
        if item["path"] == "/api/update/autoupdate" and item["body"] != b""
    )

    assert storage_request == {
        "method": "POST",
        "path": "/api/storage/rename",
        "params": {"old_path": "/ext/a.txt", "new_path": "/ext/b.txt"},
        "body": b"",
    }
    assert log_dump_request == {
        "method": "POST",
        "path": "/api/log_dump",
        "params": {"filename": "dump"},
        "body": b"",
    }
    autoupdate_body = autoupdate_put["body"]
    assert isinstance(autoupdate_body, bytes)
    assert json.loads(autoupdate_body) == {"is_enabled": False}


def test_display_rectangle_payload_matches_openapi() -> None:
    """
    Ensure display draw serializes newly documented rectangle and LED fields.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": request.content,
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    response = client.display_draw(
        {
            "application_name": "my_app",
            "priority": 90,
            "led_notification_color": "red",
            "elements": [
                {
                    "id": "text",
                    "type": "text",
                    "text": "Hello",
                    "font": "normal",
                    "x": 1,
                    "y": 2,
                    "scroll_start_delay": 1000,
                    "scroll_repeat_delay": 2500,
                },
                {
                    "id": "rect",
                    "type": "rectangle",
                    "width": 10,
                    "height": 5,
                    "radius": 2,
                    "fill": "gradient_h",
                    "fill_colors": ["#FF0000FF", "blue"],
                    "border_width": 2,
                    "border_color": (0, 255, 0, 0.5),
                },
                {
                    "id": "image",
                    "type": "image",
                    "path": "data.png",
                    "opacity": 75,
                },
            ],
        }
    )

    assert response.result == "OK"
    assert seen[0]["method"] == "POST"
    assert seen[0]["path"] == "/api/display/draw"
    body = seen[0]["body"]
    assert isinstance(body, bytes)
    assert json.loads(body) == {
        "application_name": "my_app",
        "priority": 90,
        "led_notification_color": "#FF0000FF",
        "elements": [
            {
                "id": "text",
                "x": 1,
                "y": 2,
                "display": "front",
                "type": "text",
                "text": "Hello",
                "font": "normal",
                "scroll_start_delay": 1000,
                "scroll_repeat_delay": 2500,
            },
            {
                "id": "rect",
                "x": 0,
                "y": 0,
                "display": "front",
                "type": "rectangle",
                "width": 10,
                "height": 5,
                "radius": 2,
                "fill": "gradient_h",
                "fill_colors": ["#FF0000FF", "#0000FFFF"],
                "border_width": 2,
                "border_color": "#00FF0080",
            },
            {
                "id": "image",
                "x": 0,
                "y": 0,
                "display": "front",
                "type": "image",
                "path": "data.png",
                "opacity": 75,
            },
        ],
    }


def test_display_payload_validation_matches_openapi_discriminator() -> None:
    """
    Reject missing element types, empty element lists, and invalid fill colors.
    """
    with pytest.raises(exceptions.BusyBarResponseValidationError):
        types.DisplayElements.model_validate(
            {"application_name": "my_app", "elements": [{"id": "bare"}]}
        )

    with pytest.raises(exceptions.BusyBarResponseValidationError):
        types.DisplayElements.model_validate(
            {"application_name": "my_app", "elements": []}
        )

    with pytest.raises(exceptions.BusyBarResponseValidationError):
        types.DisplayElements.model_validate(
            {
                "application_name": "my_app",
                "elements": [
                    {
                        "id": "rect",
                        "type": "rectangle",
                        "width": 10,
                        "height": 5,
                        "fill_colors": ["red", None],
                    }
                ],
            }
        )

    with pytest.raises(exceptions.BusyBarResponseValidationError):
        types.DisplayElements.model_validate(
            {
                "application_name": "my_app",
                "elements": [
                    {
                        "id": "rect",
                        "type": "rectangle",
                        "width": 10,
                        "height": 5,
                        "fill_colors": "red",
                    }
                ],
            }
        )

    display = types.DisplayElements.model_validate(
        {
            "application_name": "my_app",
            "elements": [
                {
                    "id": "text",
                    "type": "text",
                    "text": "Hello",
                    "font": "normal",
                    "scroll_rate": 0,
                }
            ],
        }
    )
    text = display.elements[0]
    assert isinstance(text, types.TextElement)
    assert text.scroll_rate == 0


def test_smart_home_sync_requests_match_openapi() -> None:
    """
    Ensure smart home helpers use documented pairing and switch endpoints.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": request.content,
            }
        )
        if request.url.path == "/api/smart_home/pairing" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "fabric_count": 1,
                    "latest_pairing_status": {
                        "value": "completed_successfully",
                        "timestamp": 1769436711,
                    },
                },
            )
        if request.url.path == "/api/smart_home/pairing" and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "available_until": "1769437579000",
                    "qr_code": "MT:YNDA0-O913..VV7I000",
                    "manual_code": "1155-360-0377",
                },
            )
        if request.url.path == "/api/smart_home/switch" and request.method == "GET":
            return httpx.Response(200, json={"state": False})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    assert client.smart_home_pairing().fabric_count == 1
    assert client.smart_home_pairing_start().manual_code == "1155-360-0377"
    assert client.smart_home_pairing_stop().result == "OK"
    assert client.smart_home_switch().state is False
    assert client.smart_home_switch_set(True, startup="last").result == "OK"

    assert [item["path"] for item in seen] == [
        "/api/smart_home/pairing",
        "/api/smart_home/pairing",
        "/api/smart_home/pairing",
        "/api/smart_home/switch",
        "/api/smart_home/switch",
    ]
    switch_body = seen[-1]["body"]
    assert isinstance(switch_body, bytes)
    assert json.loads(switch_body) == {"state": True, "startup": "last"}


@pytest.mark.asyncio
async def test_async_new_openapi_helpers() -> None:
    """
    Ensure async wrappers expose representative newly documented endpoints.
    """
    seen: list[str] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/account/backend":
            return httpx.Response(
                200,
                json={
                    "server_url": "default",
                    "client_cert_type": "default",
                    "ignore_server_cert": False,
                },
            )
        if request.url.path == "/api/busy/profiles/busy":
            return httpx.Response(200, json=_busy_profile_payload())
        if request.url.path == "/api/smart_home/switch":
            return httpx.Response(200, json={"state": True})
        if request.url.path == "/api/log_dump":
            return httpx.Response(200, json={"result": "OK", "path": "/ext/log.txt"})
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    assert (await client.account_backend()).server_url == "default"
    assert (await client.busy_profile("busy")).title == "Focus"
    assert (await client.smart_home_switch()).state is True
    assert (await client.storage_rename("/a", "/b")).result == "OK"
    log_dump = await client.log_dump()
    assert log_dump.result == "OK"
    assert log_dump.path == "/ext/log.txt"
    await client.aclose()

    assert seen == [
        "GET /api/account/backend",
        "GET /api/busy/profiles/busy",
        "GET /api/smart_home/switch",
        "POST /api/storage/rename",
        "POST /api/log_dump",
    ]


def test_response_alias_models_accept_openapi_and_legacy_fields() -> None:
    """
    Validate response aliases introduced by the firmware OpenAPI refresh.
    """
    account = types.AccountState.model_validate({"status": "connected"})
    legacy_account = types.AccountState.model_validate({"state": "disconnected"})
    conflict_account = types.AccountState.model_validate(
        {"status": "connected", "state": "error"}
    )
    ble = types.BleStatus.model_validate({"status": "connected", "address": "AA"})
    legacy_ble = types.BleStatus.model_validate({"state": "connectable"})
    update = types.UpdateStatus.model_validate(
        {"check": {"available_version": "1.2.3", "status": "available"}}
    )
    legacy_update = types.UpdateCheckStatus.model_validate({"result": "failure"})

    assert account.status == "connected"
    assert account.state == "connected"
    assert account.model_dump(exclude_none=True) == {"status": "connected"}
    assert legacy_account.status == "disconnected"
    assert conflict_account.status == "connected"
    assert conflict_account.state == "connected"
    assert ble.status == "connected"
    assert ble.state == "connected"
    assert ble.model_dump(exclude_none=True) == {"status": "connected", "address": "AA"}
    assert legacy_ble.status == "connectable"
    assert update.check is not None
    assert update.check.status == "available"
    assert update.check.result == "available"
    assert update.check.model_dump(exclude_none=True) == {
        "available_version": "1.2.3",
        "status": "available",
    }
    assert legacy_update.status == "failure"


def test_response_models_keep_firmware_strings_forward_compatible() -> None:
    """
    Ensure firmware response strings stay opaque for forward compatibility.
    """
    firmware = types.StatusFirmware.model_validate(
        {"build_date": "2026-06-19T12:00:00", "target": 22}
    )
    transport = types.NetworkInterfaceInfo.model_validate({"type": "ethernet"})
    backend = types.AccountBackend.model_validate(
        {
            "server_url": "default",
            "client_cert_type": "future-cert",
            "ignore_server_cert": False,
        }
    )
    pairing = types.SmartHomePairingStatus.model_validate({"value": "in_progress"})
    switch = types.SmartHomeSwitchState.model_validate(
        {"state": True, "startup": "schedule"}
    )
    update = types.UpdateStatus.model_validate(
        {
            "install": {"event": "future_event", "action": "future_action"},
            "check": {"status": "future_status"},
        }
    )

    assert firmware.build_date == "2026-06-19T12:00:00"
    assert transport.type == "ethernet"
    assert backend.client_cert_type == "future-cert"
    assert pairing.value == "in_progress"
    assert switch.startup == "schedule"
    assert update.install is not None
    assert update.install.event == "future_event"
    assert update.install.action == "future_action"
    assert update.check is not None
    assert update.check.status == "future_status"
