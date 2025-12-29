import json
from typing import Callable

import httpx
import pytest

from busylib import BusyBar, exceptions, types


Responder = Callable[[httpx.Request], httpx.Response]


def make_client(responder: Responder, **kwargs) -> BusyBar:
    transport = httpx.MockTransport(responder)
    return BusyBar(addr="http://device.local", transport=transport, **kwargs)


def test_init_defaults_local():
    client = BusyBar()
    assert client.base_url == "http://10.0.4.20"
    assert client.client.base_url == httpx.URL("http://10.0.4.20")


def test_init_token_sets_cloud_base_and_header():
    client = BusyBar(token="secret")
    assert client.base_url == "https://proxy.dev.busy.app"
    assert client.client.headers["authorization"] == "Bearer secret"


def test_get_version_success():
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(
            200,
            json={
                "api_semver": "1.2.0",
                "version": "1.2.0+build",
                "branch": "main",
            },
        )

    client = make_client(responder, api_version="1.2.0")
    result = client.get_version()
    assert isinstance(result, types.VersionInfo)
    assert result.api_semver == "1.2.0"
    assert result.branch == "main"


def test_error_response_raises_api_error():
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "fail", "code": 500})

    client = make_client(responder)
    with pytest.raises(exceptions.BusyBarAPIError) as exc:
        client.get_version()
    assert exc.value.code == 500
    assert "fail" in str(exc.value)


def test_plain_text_error_response():
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = make_client(responder)
    with pytest.raises(exceptions.BusyBarAPIError) as exc:
        client.get_version()
    assert exc.value.code == 404
    assert "HTTP 404" in str(exc.value)


def test_get_version_incompatible_requires_device_update():
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"api_semver": "0.9.0"})

    client = make_client(responder, api_version="1.0.0")
    with pytest.raises(exceptions.BusyBarAPIVersionError) as exc:
        client.get_version()
    assert "update firmware" in str(exc.value)


def test_request_carries_api_version_header():
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["header"] = request.headers.get("x-busy-api-version")
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder, api_version="1.1.0")
    resp = client.enable_wifi()
    assert resp.result == "OK"
    assert seen["header"] == "1.1.0"


def test_retry_on_transport_error():
    calls = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder, max_retries=1, backoff=0.0)
    resp = client.enable_wifi()
    assert resp.result == "OK"
    assert calls["count"] == 2


def test_draw_on_display_sends_utf8_body():
    payload = {
        "app_id": "demo",
        "elements": [
            {
                "id": "1",
                "type": "text",
                "x": 0,
                "y": 0,
                "text": "Съешь ещё этих мягких булок",
                "display": "front",
            }
        ],
    }

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"].startswith("application/json")
        body = request.content.decode("utf-8")
        assert "Съешь" in body  # ensure ensure_ascii=False
        # ensure no \u0421 escaping
        assert "\\u0421" not in body
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = client.draw_on_display(payload)
    assert resp.result == "OK"


def test_get_screen_frame_returns_bytes():
    expected = b"\x00\x01\x02"

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/screen"
        assert request.url.params["display"] == "1"
        return httpx.Response(200, content=expected)

    client = make_client(responder)
    data = client.get_screen_frame(1)
    assert data == expected


@pytest.mark.parametrize(
    "method,path",
    [
        ("play_audio", "/api/audio/play"),
        ("stop_audio", "/api/audio/play"),
        ("clear_display", "/api/display/draw"),
        ("remove_storage_file", "/api/storage/remove"),
        ("create_storage_directory", "/api/storage/mkdir"),
        ("delete_app_assets", "/api/assets/upload"),
        ("enable_wifi", "/api/wifi/enable"),
        ("disable_wifi", "/api/wifi/disable"),
        ("disconnect_wifi", "/api/wifi/disconnect"),
        ("ble_enable", "/api/ble/enable"),
        ("ble_disable", "/api/ble/disable"),
        ("ble_forget_pairing", "/api/ble/pairing"),
    ],
)
def test_simple_success_methods(method: str, path: str):
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == path
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    func = getattr(client, method)
    # supply required args when needed
    if method == "play_audio":
        resp = func("app", "file")
    elif method in {"remove_storage_file", "create_storage_directory"}:
        resp = func("/tmp")
    elif method == "delete_app_assets":
        resp = func("app")
    elif method == "disconnect_wifi":
        resp = func()
    else:
        resp = func()
    assert resp.result == "OK"


def test_connect_wifi_serialization():
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": "OK"})

    cfg = {"ssid": "TestNetwork", "password": "secret", "security": "WPA2"}
    client = make_client(responder)
    resp = client.connect_wifi(cfg)
    assert resp.result == "OK"
    assert seen["body"]["ssid"] == "TestNetwork"
    assert seen["body"]["security"] == "WPA2"


def test_display_brightness_validation_and_payload():
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["content"] = request.content
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = client.set_display_brightness(front="auto", back=50)
    assert resp.result == "OK"
    assert seen["params"] == {"front": "auto", "back": "50"}
    assert seen["content"] == b""

    with pytest.raises(ValueError):
        client.set_display_brightness(front="invalid")  # type: ignore[arg-type]


def test_set_audio_volume_params():
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["content"] = request.content
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = client.set_audio_volume(42.5)
    assert resp.result == "OK"
    assert seen["params"] == {"volume": "42.5"}
    assert seen["content"] == b""


def test_draw_on_display_color_serialization():
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    display = types.DisplayElements(
        app_id="app",
        elements=[
            types.TextElement(
                id="t1",
                type="text",
                x=0,
                y=0,
                text="hi",
                color="rgba(255, 0, 0, 0.5)",
                display=types.DisplayName.FRONT,
            )
        ],
    )
    resp = client.draw_on_display(display)
    assert resp.result == "OK"
    color = seen["body"]["elements"][0]["color"]
    assert color == "#FF000080"


def test_draw_on_display_color_tuple_alpha():
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    display = types.DisplayElements(
        app_id="app",
        elements=[
            types.TextElement(
                id="t2",
                type="text",
                x=0,
                y=0,
                text="hi",
                color=(255, 255, 255, 100),
                display=types.DisplayName.FRONT,
            )
        ],
    )
    resp = client.draw_on_display(display)
    assert resp.result == "OK"
    color = seen["body"]["elements"][0]["color"]
    assert color == "#FFFFFF64"
