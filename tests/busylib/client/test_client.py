import json
from typing import Callable

import httpx
import pytest

from busylib import BusyBar, exceptions, types

Responder = Callable[[httpx.Request], httpx.Response]


def make_client(responder: Responder, **kwargs) -> BusyBar:
    """
    Build a BusyBar client backed by an HTTPX mock transport.

    Keeps transport setup consistent across tests.
    """
    transport = httpx.MockTransport(responder)
    return BusyBar(addr="http://device.local", transport=transport, **kwargs)


def test_init_defaults_local():
    """
    Verify the default base URL points to the device LAN address.

    Ensures base_url and HTTPX client base_url match.
    """
    client = BusyBar()
    assert client.base_url == "http://10.0.4.20"
    assert client.client.base_url == httpx.URL("http://10.0.4.20")


def test_init_token_sets_cloud_base_and_header():
    """
    Ensure token auth switches to the cloud proxy base URL.

    Also validates the Authorization header value.
    """
    client = BusyBar(token="secret")
    assert client.base_url == "https://proxy.busy.app"
    assert client.client.headers["authorization"] == "Bearer secret"


def test_get_version_success():
    """
    Validate successful parsing of version information.

    Confirms the version and branch fields are mapped.
    """

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


def test_get_device_name_and_time():
    """
    Fetch device name and time from their respective endpoints.

    Verifies both responses are parsed correctly.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/name":
            return httpx.Response(200, json={"name": "BusyBar"})
        if request.url.path == "/api/time":
            return httpx.Response(200, json={"timestamp": "2024-01-01T10:00:00"})
        return httpx.Response(404, json={"error": "missing", "code": 404})

    client = make_client(responder)
    name = client.get_device_name()
    assert name.name == "BusyBar"
    time_info = client.get_device_time()
    assert time_info.timestamp == "2024-01-01T10:00:00"


def test_set_device_name() -> None:
    """
    Send device name update payload via POST /api/name.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = client.set_device_name("Busy Desk")
    assert resp.result == "OK"
    assert seen["path"] == "/api/name"
    assert seen["method"] == "POST"
    assert seen["body"] == {"name": "Busy Desk"}


def test_set_device_name_rejects_empty() -> None:
    """
    Reject empty device names before sending request.
    """
    client = make_client(lambda _request: httpx.Response(200, json={"result": "OK"}))
    with pytest.raises(ValueError):
        client.set_device_name("")


def test_get_account_info():
    """
    Parse linked account info from the client.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/info"
        return httpx.Response(200, json={"linked": True, "email": "name@example.com"})

    client = make_client(responder)
    result = client.get_account_info()
    assert result.linked is True
    assert result.email == "name@example.com"


def test_set_account_profile() -> None:
    """
    Ensure account profile updates are sent as query params.
    """
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = client.set_account_profile("custom", custom_url="mqtts://mqtt.example.com")
    assert resp.result == "OK"
    assert seen["params"] == {
        "profile": "custom",
        "custom_url": "mqtts://mqtt.example.com",
    }


def test_link_account():
    """
    Parse account link response from the client.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/link"
        return httpx.Response(200, json={"code": "ABCD", "expires_at": 1700000000})

    client = make_client(responder)
    result = client.link_account()
    assert result.code == "ABCD"
    assert result.expires_at == 1700000000


def test_error_response_raises_api_error():
    """
    Raise BusyBarAPIError on JSON error responses.

    Ensures error payload is surfaced through the exception.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": "fail", "code": 500},
            headers={"X-Request-ID": "req-500"},
        )

    client = make_client(responder)
    with pytest.raises(exceptions.BusyBarAPIError) as exc:
        client.get_version()
    assert exc.value.code == 500
    assert exc.value.status_code == 500
    assert exc.value.method == "GET"
    assert exc.value.path == "/api/version"
    assert exc.value.request_id == "req-500"
    assert exc.value.response_excerpt == '{"error":"fail","code":500}'
    assert "fail" in str(exc.value)


def test_api_error_has_truncated_excerpt() -> None:
    """
    Keep response excerpt compact for diagnostic fields in API errors.
    """

    def responder(_request: httpx.Request) -> httpx.Response:
        long_text = "x" * 400
        return httpx.Response(503, text=long_text)

    client = make_client(responder)
    with pytest.raises(exceptions.BusyBarAPIError) as exc:
        client.get_version()
    assert exc.value.response_excerpt is not None
    assert exc.value.response_excerpt.endswith("...")
    assert len(exc.value.response_excerpt) <= 259


def test_plain_text_error_response():
    """
    Raise BusyBarAPIError on plain-text error responses.

    Confirms non-JSON failures still propagate with HTTP status.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = make_client(responder)
    with pytest.raises(exceptions.BusyBarAPIError) as exc:
        client.get_version()
    assert exc.value.code == 404
    assert "HTTP 404" in str(exc.value)


def test_get_version_incompatible_requires_device_update():
    """
    Reject incompatible firmware API versions.

    Ensures the version guard raises a dedicated error.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"api_semver": "0.9.0"})

    client = make_client(responder, api_version="1.0.0")
    with pytest.raises(exceptions.BusyBarAPIVersionError) as exc:
        client.get_version()
    assert "update firmware" in str(exc.value)


def test_request_carries_api_version_header():
    """
    Send API version header with each request.

    Verifies the header is derived from client configuration.
    """
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["header"] = request.headers.get("x-busy-api-version")
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder, api_version="1.1.0")
    resp = client.enable_wifi()
    assert resp.result == "OK"
    assert seen["header"] == "1.1.0"


def test_retry_on_transport_error():
    """
    Retry transient transport failures when configured.

    Ensures the second attempt succeeds after a connection error.
    """
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


def test_response_validation_error_is_wrapped() -> None:
    """
    Wrap model validation failures into BusyBarResponseValidationError.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(
            200,
            json={"api_semver": "1.2.0", "build_date": {"invalid": True}},
        )

    client = make_client(responder, api_version="1.2.0")
    with pytest.raises(exceptions.BusyBarResponseValidationError) as exc:
        client.get_version()
    assert exc.value.model == "VersionInfo"


def test_all_library_errors_inherit_base_error() -> None:
    """
    Ensure all public exception types share a single base class.
    """
    assert issubclass(exceptions.BusyBarAPIError, exceptions.BusyBarError)
    assert issubclass(exceptions.BusyBarRequestError, exceptions.BusyBarError)
    assert issubclass(exceptions.BusyBarAPIVersionError, exceptions.BusyBarError)
    assert issubclass(exceptions.BusyBarUsbError, exceptions.BusyBarError)
    assert issubclass(exceptions.BusyBarProtocolError, exceptions.BusyBarError)
    assert issubclass(
        exceptions.BusyBarResponseValidationError,
        exceptions.BusyBarError,
    )
    assert issubclass(exceptions.BusyBarConversionError, exceptions.BusyBarError)
    assert issubclass(exceptions.BusyBarWebSocketError, exceptions.BusyBarError)


def test_draw_on_display_sends_utf8_body():
    """
    Ensure JSON payloads are encoded as UTF-8 without ASCII escaping.

    This keeps non-ASCII text readable on the device.
    """
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
    """
    Return raw bytes for screen frame requests.

    Confirms binary content is not JSON-decoded.
    """
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
    """
    Verify simple methods hit expected endpoints and succeed.

    Covers a set of API methods with uniform response handling.
    """

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
    """
    Serialize Wi-Fi configuration into JSON payload.

    Ensures the expected fields are present in the request body.
    """
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
    """
    Validate display brightness parameters and payload shape.

    Confirms query params and empty body are sent as expected.
    """
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
    """
    Validate audio volume query parameters.

    Ensures body is empty and volume is passed via params.
    """
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
    """
    Serialize color strings into hex RGBA values.

    Confirms color conversion in display elements.
    """
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    elements: list[types.DisplayElement] = [
        types.TextElement(
            id="t1",
            type="text",
            x=0,
            y=0,
            text="hi",
            color="rgba(255, 0, 0, 0.5)",
            display=types.DisplayName.FRONT,
        )
    ]
    display = types.DisplayElements(
        app_id="app",
        elements=elements,
    )
    resp = client.draw_on_display(display)
    assert resp.result == "OK"
    color = seen["body"]["elements"][0]["color"]
    assert color == "#FF000080"


def test_draw_on_display_color_tuple_alpha():
    """
    Serialize color tuples with alpha into hex RGBA values.

    Ensures tuple-based colors are handled consistently.
    """
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    elements: list[types.DisplayElement] = [
        types.TextElement(
            id="t2",
            type="text",
            x=0,
            y=0,
            text="hi",
            color=(255, 255, 255, 100),
            display=types.DisplayName.FRONT,
        )
    ]
    display = types.DisplayElements(
        app_id="app",
        elements=elements,
    )
    resp = client.draw_on_display(display)
    assert resp.result == "OK"
    color = seen["body"]["elements"][0]["color"]
    assert color == "#FFFFFF64"
