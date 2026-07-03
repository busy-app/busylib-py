import json
from typing import Callable

import httpx
import pytest
from pydantic import ValidationError

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


def test_version_success():
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
    result = client.version()
    assert isinstance(result, types.VersionInfo)
    assert result.api_semver == "1.2.0"
    assert result.branch == "main"


def test_version_default_api_version_remains_device_semver() -> None:
    """
    Keep the default API compatibility header on the device semver track.
    """
    seen: dict[str, str | None] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["header"] = request.headers.get("x-busy-api-version")
        return httpx.Response(200, json={"api_semver": "0.1.0"})

    client = make_client(responder)
    result = client.version()

    assert result.api_semver == "0.1.0"
    assert seen["header"] == "0.1.0"


def test_name_and_time():
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
    name = client.name()
    assert name.name == "BusyBar"
    time_info = client.time()
    assert time_info.timestamp == "2024-01-01T10:00:00"


def test_name_set() -> None:
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
    resp = client.name_set("Busy Desk")
    assert resp.result == "OK"
    assert seen["path"] == "/api/name"
    assert seen["method"] == "POST"
    assert seen["body"] == {"name": "Busy Desk"}


def test_name_set_rejects_empty() -> None:
    """
    Reject empty device names before sending request.
    """
    client = make_client(lambda _request: httpx.Response(200, json={"result": "OK"}))
    with pytest.raises(ValueError):
        client.name_set("")


def test_account_info():
    """
    Parse linked account info from the client.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/info"
        return httpx.Response(200, json={"linked": True, "email": "name@example.com"})

    client = make_client(responder)
    result = client.account_info()
    assert result.linked is True
    assert result.email == "name@example.com"


def test_account_profile_set() -> None:
    """
    Ensure account profile updates are sent as query params.
    """
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = client.account_profile_set("custom", custom_url="mqtts://mqtt.example.com")
    assert resp.result == "OK"
    assert seen["params"] == {
        "profile": "custom",
        "custom_url": "mqtts://mqtt.example.com",
    }


def test_account_link():
    """
    Parse account link response from the client.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/account/link"
        return httpx.Response(200, json={"code": "ABCD", "expires_at": 1700000000})

    client = make_client(responder)
    result = client.account_link()
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
        client.version()
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
        client.version()
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
        client.version()
    assert exc.value.code == 404
    assert "HTTP 404" in str(exc.value)


def test_version_incompatible_warns_by_default(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Warn by default instead of blocking callers on API version mismatch.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"api_semver": "0.9.0"})

    client = make_client(responder, api_version="1.0.0")
    result = client.version()

    assert result.api_semver == "0.9.0"
    assert "update firmware" in caplog.text


def test_version_incompatible_strict_requires_device_update():
    """
    Reject incompatible firmware API versions in strict mode.

    Ensures the version guard raises a dedicated error.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"api_semver": "0.9.0"})

    client = make_client(
        responder,
        api_version="1.0.0",
        compatibility_mode="strict",
    )
    with pytest.raises(exceptions.BusyBarAPIVersionError) as exc:
        client.version()
    assert "update firmware" in str(exc.value)


def test_version_incompatible_can_skip_compatibility_check() -> None:
    """
    Allow callers to opt out from compatibility checks.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"api_semver": "0.9.0"})

    client = make_client(
        responder,
        api_version="1.0.0",
        compatibility_mode="none",
    )
    result = client.version()

    assert result.api_semver == "0.9.0"


def test_client_rejects_unknown_compatibility_mode() -> None:
    """
    Validate compatibility policy names at client construction.
    """
    with pytest.raises(ValueError):
        make_client(lambda _request: httpx.Response(200), compatibility_mode="fail")


def test_method_compatibility_metadata() -> None:
    """
    Expose declarative OpenAPI metadata for version-gated helpers.
    """
    client = make_client(lambda _request: httpx.Response(200, json={"result": "OK"}))
    metadata = client.method_compatibility("log_dump")

    assert metadata == {
        "version": "24.3.0",
        "path": "/api/log_dump",
        "method": "POST",
    }
    assert client.method_compatibility("missing") is None


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
    resp = client.wifi_enable()
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
    resp = client.wifi_enable()
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
        client.version()
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


def test_delivery_error_helpers_format_and_classify_errors() -> None:
    """
    Validate delivery error diagnostics and retryability helpers.
    """

    bad_request = exceptions.BusyBarAPIError(
        "invalid payload",
        status_code=400,
        method="POST",
        path="/api/display/draw",
        request_id="req-1",
        response_excerpt='{"error":"invalid payload"}',
    )
    server_error = exceptions.BusyBarAPIError(
        "proxy unavailable",
        status_code=503,
        method="POST",
        path="/api/display/draw",
    )
    request_error = exceptions.BusyBarRequestError(
        "connection failed",
        method="POST",
        path="/api/audio/play",
        attempts=2,
    )

    assert not exceptions.is_retryable_delivery_error(bad_request)
    assert exceptions.is_retryable_delivery_error(server_error)
    assert exceptions.is_retryable_delivery_error(request_error)
    assert (
        exceptions.format_delivery_error(bad_request)
        == "HTTP 400 | POST /api/display/draw | invalid payload | "
        'request_id=req-1 | body={"error":"invalid payload"}'
    )
    assert (
        exceptions.format_delivery_error(request_error)
        == "request error | POST /api/audio/play | attempts=2 | connection failed"
    )


def test_display_draw_sends_utf8_body():
    """
    Ensure JSON payloads are encoded as UTF-8 without ASCII escaping.

    This keeps non-ASCII text readable on the device.
    """
    payload = {
        "application_name": "demo",
        "elements": [
            {
                "id": "1",
                "type": "text",
                "x": 0,
                "y": 0,
                "text": "Cafe creme",
                "font": "small",
                "display": "front",
            }
        ],
    }

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"].startswith("application/json")
        body = request.content.decode("utf-8")
        assert "Cafe creme" in body  # ensure ensure_ascii=False
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    resp = client.display_draw(payload)
    assert resp.result == "OK"


def test_display_draw_and_clear_params() -> None:
    """
    Validate display_draw and display_clear request params and session header.
    """

    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
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
    draw_resp = client.display_draw(payload, session_id="bar-1")
    clear_resp = client.display_clear(
        application_name="demo",
        session_id="bar-1",
    )
    assert draw_resp.result == "OK"
    assert clear_resp.result == "OK"
    assert seen[0]["path"] == "/api/display/draw"
    assert seen[0]["method"] == "POST"
    assert seen[0]["session"] == "bar-1"
    assert seen[1]["path"] == "/api/display/draw"
    assert seen[1]["method"] == "DELETE"
    assert seen[1]["params"] == {"application_name": "demo"}
    assert seen[1]["session"] == "bar-1"


def test_display_draw_can_clear_before_draw() -> None:
    """
    Validate clear_before_draw in display_draw.
    """

    seen: list[tuple[str, str, dict[str, str]]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"result": "OK"})

    client = make_client(responder)
    payload = {
        "application_name": "demo",
        "elements": [
            {"id": "1", "type": "text", "x": 0, "y": 0, "text": "A", "font": "small"}
        ],
    }
    resp = client.display_draw(payload, clear_before_draw=True)
    assert resp.result == "OK"
    assert seen[0] == (
        "DELETE",
        "/api/display/draw",
        {},
    )
    assert seen[1][0] == "POST"


def test_display_can_clear_draw_and_audio_play() -> None:
    """
    Validate high-level display flow: clear, draw, and audio_play.
    """

    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
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
    resp = client.display(
        payload,
        session_id="bar-1",
        clear_before_draw=True,
        audio_payload={"stock_path": "shared/sfx.snd"},
    )
    assert resp.result == "OK"
    assert seen == [
        {
            "method": "DELETE",
            "path": "/api/display/draw",
            "params": {},
            "body": None,
            "session": "bar-1",
        },
        {
            "method": "POST",
            "path": "/api/display/draw",
            "params": {},
            "body": normalized_payload,
            "session": "bar-1",
        },
        {
            "method": "POST",
            "path": "/api/audio/play",
            "params": {},
            "body": {"stock_path": "shared/sfx.snd"},
            "session": "bar-1",
        },
    ]


def test_display_draw_can_sanitize_text_payload(caplog) -> None:
    """
    Validate sanitize_text for sync display_draw.
    """

    seen: dict[str, str] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8")
        seen["body"] = body
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
    resp = client.display_draw(payload, sanitize_text=True)
    assert resp.result == "OK"
    assert "Demo meeting" in seen["body"]
    assert "🚀" not in seen["body"]
    assert (
        "Sanitized display text element_id=1 display=front "
        "text_before='Demo 🚀\\nmeeting' text_after='Demo meeting'"
    ) in caplog.text


def test_screen_returns_bytes():
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
    data = client.screen(1)
    assert data == expected


@pytest.mark.parametrize(
    "method,path",
    [
        ("audio_play", "/api/audio/play"),
        ("audio_stop", "/api/audio/play"),
        ("display_clear", "/api/display/draw"),
        ("storage_remove", "/api/storage/remove"),
        ("storage_mkdir", "/api/storage/mkdir"),
        ("assets_delete", "/api/assets/upload"),
        ("wifi_enable", "/api/wifi/enable"),
        ("wifi_disable", "/api/wifi/disable"),
        ("wifi_disconnect", "/api/wifi/disconnect"),
        ("ble_enable", "/api/ble/enable"),
        ("ble_disable", "/api/ble/disable"),
        ("ble_pairing_forget", "/api/ble/pairing"),
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
    if method == "audio_play":
        resp = func(path="file")
    elif method in {"storage_remove", "storage_mkdir"}:
        resp = func("/tmp")
    elif method == "assets_delete":
        resp = func("app")
    elif method == "wifi_disconnect":
        resp = func()
    else:
        resp = func()
    assert resp.result == "OK"


def test_wifi_connect_serialization():
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
    resp = client.wifi_connect(cfg)
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
    resp = client.display_brightness_set("auto")
    assert resp.result == "OK"
    assert seen["params"] == {"value": "auto"}
    assert seen["content"] == b""

    with pytest.raises(ValueError):
        client.display_brightness_set("invalid")  # type: ignore[arg-type]


def test_audio_volume_set_params():
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
    resp = client.audio_volume_set(42.5)
    assert resp.result == "OK"
    assert seen["params"] == {"volume": "42.5"}
    assert seen["content"] == b""


def test_display_draw_color_serialization():
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
            font="small",
            color="rgba(255, 0, 0, 0.5)",
            display=types.DisplayName.FRONT,
        )
    ]
    display = types.DisplayElements(
        application_name="app",
        elements=elements,
    )
    resp = client.display_draw(display)
    assert resp.result == "OK"
    color = seen["body"]["elements"][0]["color"]
    assert color == "#FF000080"


def test_text_element_accepts_current_font_names() -> None:
    """
    Validate font names supported by the current display API.

    Firmware API 22 rejects the old medium/medium_condensed/big names.
    """
    for font in (
        "tiny",
        "small",
        "normal",
        "condensed",
        "bold",
        "large",
        "extra_large",
        "global",
    ):
        element = types.TextElement(
            id=f"text-{font}",
            type="text",
            x=0,
            y=0,
            text="hi",
            font=font,
        )
        assert element.font == font


@pytest.mark.parametrize("font", ["medium", "medium_condensed", "big"])
def test_text_element_rejects_legacy_font_names(font: str) -> None:
    """
    Reject font names removed from the current display API.

    This catches payload regressions that firmware returns as HTTP 400.
    """
    with pytest.raises(ValidationError):
        types.TextElement(
            id=f"text-{font}",
            type="text",
            x=0,
            y=0,
            text="hi",
            font=font,  # type: ignore[reportArgumentType]
        )


def test_display_draw_color_tuple_alpha():
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
            font="small",
            color=(255, 255, 255, 100),
            display=types.DisplayName.FRONT,
        )
    ]
    display = types.DisplayElements(
        application_name="app",
        elements=elements,
    )
    resp = client.display_draw(display)
    assert resp.result == "OK"
    color = seen["body"]["elements"][0]["color"]
    assert color == "#FFFFFF64"
