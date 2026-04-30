from __future__ import annotations

import httpx
import pytest

from busylib import AsyncBusyBar, BusyBar, exceptions, types
from busylib.client import input as input_client


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


def test_send_input_key_sync() -> None:
    """
    Ensure sync input key events send the correct key parameter.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "params": dict(request.url.params),
                "method": request.method,
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.send_input_key(types.InputKey.OK)
    assert resp.result == "OK"
    assert seen == [{"path": "/api/input", "params": {"key": "ok"}, "method": "POST"}]


@pytest.mark.asyncio
async def test_send_input_key_async() -> None:
    """
    Ensure async input key events send the correct key parameter.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "params": dict(request.url.params),
                "method": request.method,
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.send_input_key(types.InputKey.OK)
    assert resp.result == "OK"
    await client.aclose()
    assert seen == [{"path": "/api/input", "params": {"key": "ok"}, "method": "POST"}]


class DummyWebSocket:
    """
    Minimal async websocket stub for input stream tests.

    It yields a deterministic sequence of text and binary events.
    """

    def __init__(self) -> None:
        """
        Initialize deterministic websocket messages.
        """
        self._messages: list[bytes | str] = ['{"key":"ok","state":"press"}', b"\x01"]

    async def __aenter__(self) -> "DummyWebSocket":
        """
        Enter websocket async context and return self.
        """
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        """
        Exit websocket async context without suppressing errors.
        """
        return False

    def __aiter__(self):
        """
        Yield prepared websocket messages and then finish.
        """

        async def _iter():
            """
            Iterate through all prepared websocket messages.
            """
            for message in self._messages:
                yield message

        return _iter()


@pytest.mark.asyncio
async def test_stream_input_ws_uses_query_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure input websocket stream forwards API token in query string.

    The method should return both text and binary events as-is.
    """
    captured: dict[str, object] = {}

    def fake_connect(url: str, **kwargs):
        """
        Capture websocket connection parameters for assertions.
        """
        captured["url"] = url
        captured["headers"] = kwargs.get("additional_headers")
        captured["extra"] = kwargs
        return DummyWebSocket()

    monkeypatch.setattr(input_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr="http://device.local", token="secret")
    events: list[bytes | str] = []
    async for message in client.stream_input_ws():
        events.append(message)
    await client.aclose()

    url = captured.get("url")
    extra = captured.get("extra")

    assert isinstance(url, str)
    assert "x-api-token=secret" in url
    assert captured.get("headers") is None
    assert isinstance(extra, dict)
    assert extra.get("max_size") is None
    assert extra.get("ping_interval") is None
    assert events == ['{"key":"ok","state":"press"}', b"\x01"]


@pytest.mark.asyncio
async def test_stream_input_ws_wraps_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure websocket failures are wrapped into BusyBarWebSocketError.
    """

    def fake_connect(_url: str, **_kwargs):
        raise RuntimeError("ws boom")

    monkeypatch.setattr(input_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr="http://device.local", token="secret")
    with pytest.raises(exceptions.BusyBarWebSocketError) as exc:
        async for _message in client.stream_input_ws():
            pass
    await client.aclose()

    assert exc.value.path == "/api/input"
    assert isinstance(exc.value.__cause__, RuntimeError)


def test_stream_input_events_ws_sync_not_implemented() -> None:
    """
    Ensure sync input events API is explicitly marked as unavailable.

    Current firmware does not provide button event broadcasting over HTTP API.
    """
    client = _make_sync_client(lambda _request: httpx.Response(200, json={"result": "OK"}))

    with pytest.raises(NotImplementedError):
        client.stream_input_events_ws()


def test_parse_input_event_message_sync_explicit_payload() -> None:
    """
    Ensure explicit JSON input event payload is parsed into typed model.

    This validates the future-proof event contract (`key` + `state`).
    """
    client = _make_sync_client(lambda _request: httpx.Response(200, json={"result": "OK"}))

    event = client.parse_input_event_message('{"key":"ok","state":"press","timestamp_ms":42}')

    assert event.key is types.InputKey.OK
    assert event.state is types.InputEventState.PRESS
    assert event.timestamp_ms == 42


def test_parse_input_event_message_sync_shorthand_payload() -> None:
    """
    Ensure shorthand JSON payload is normalized into typed InputEvent.

    The parser must support firmware-like shorthand shape (`{\"ok\":1}`).
    """
    client = _make_sync_client(lambda _request: httpx.Response(200, json={"result": "OK"}))

    event = client.parse_input_event_message('{"ok":1}')

    assert event.key is types.InputKey.OK
    assert event.state is types.InputEventState.PRESS
    assert event.timestamp_ms is None


def test_parse_input_event_message_sync_raises_protocol_error() -> None:
    """
    Ensure invalid message format is wrapped into BusyBarProtocolError.

    Callers should receive domain-level exception for parse failures.
    """
    client = _make_sync_client(lambda _request: httpx.Response(200, json={"result": "OK"}))

    with pytest.raises(exceptions.BusyBarProtocolError) as exc:
        client.parse_input_event_message("[]")

    assert exc.value.path == "/api/input/events"


@pytest.mark.asyncio
async def test_stream_input_events_ws_async_not_implemented() -> None:
    """
    Ensure async input events API is explicitly marked as unavailable.

    The method should fail fast with NotImplementedError on current firmware.
    """
    client = _make_async_client(lambda _request: httpx.Response(200, json={"result": "OK"}))

    with pytest.raises(NotImplementedError):
        async for _message in client.stream_input_events_ws():
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_parse_input_event_message_async_explicit_payload() -> None:
    """
    Ensure async client exposes the same input event parsing contract.

    The parser is sync but available on async client for convenience.
    """
    client = _make_async_client(lambda _request: httpx.Response(200, json={"result": "OK"}))

    event = client.parse_input_event_message('{"key":"back","state":"release"}')

    assert event.key is types.InputKey.BACK
    assert event.state is types.InputEventState.RELEASE
    await client.aclose()
