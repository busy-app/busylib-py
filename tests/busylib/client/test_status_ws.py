import json
from typing import Any, cast

import pytest

from busylib import AsyncBusyBar, exceptions
from busylib.client import state_stream as state_stream_client
from busylib.state_stream_proto import state_pb2


class DummyWebSocket:
    """
    Minimal async websocket stub for status stream tests.

    The stub records sent handshake payloads and yields predefined messages.
    """

    def __init__(self, messages: list[bytes | str]) -> None:
        """
        Initialize a deterministic websocket message source.
        """
        self._messages = messages
        self.sent: list[str] = []

    async def __aenter__(self) -> "DummyWebSocket":
        """
        Enter async websocket context.
        """
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        """
        Exit websocket context without suppressing exceptions.
        """
        return False

    async def send(self, payload: str) -> None:
        """
        Capture outgoing websocket payload for assertions.
        """
        self.sent.append(payload)

    def __aiter__(self):
        """
        Iterate over prepared websocket messages.
        """
        return self._iter()

    async def _iter(self):
        """
        Async generator over fixed test messages.
        """
        for item in self._messages:
            yield item


@pytest.mark.asyncio
async def test_stream_status_ws_decodes_protobuf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Decode binary protobuf payloads from /api/status/ws into dictionaries.
    """
    state_schema = cast(Any, state_pb2)
    message = state_schema.State(timestamp=123)
    update = message.updates.add()
    update.device_name.name = "BUSY"
    payload = message.SerializeToString()

    captured: dict[str, object] = {}
    ws = DummyWebSocket([payload])

    def fake_connect(url: str, **kwargs):
        """
        Capture connection arguments and return dummy websocket.
        """
        captured["url"] = url
        captured["kwargs"] = kwargs
        return ws

    monkeypatch.setattr(state_stream_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr="http://device.local", token="secret")
    items: list[dict[str, object] | bytes | str] = []
    async for item in client.stream_status_ws():
        items.append(item)
        break

    assert ws.sent == [json.dumps({"enable": True})]
    assert isinstance(items[0], dict)
    decoded = cast(dict[str, Any], items[0])
    assert decoded["timestamp"] == "123"
    assert decoded["updates"][0]["device_name"]["name"] == "BUSY"
    assert "x-api-token=secret" in str(captured["url"])
    assert isinstance(captured["kwargs"], dict)
    assert captured["kwargs"]["max_size"] == 4 * 1024 * 1024
    assert captured["kwargs"]["ping_interval"] == 20
    assert captured["kwargs"]["ping_timeout"] == 20
    await client.aclose()


@pytest.mark.asyncio
async def test_stream_status_ws_can_yield_raw_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Yield raw binary frames when protobuf decoding is disabled.
    """
    raw = b"\x01\x02\x03"

    def fake_connect(_url: str, **_kwargs):
        """
        Return a websocket that emits one raw binary frame.
        """
        return DummyWebSocket([raw])

    monkeypatch.setattr(state_stream_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr="http://device.local")
    async for item in client.stream_status_ws(decode_protobuf=False):
        assert item == raw
        break
    await client.aclose()


@pytest.mark.asyncio
async def test_stream_status_ws_wraps_decode_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Wrap protobuf decode failures into BusyBarProtocolError.
    """

    def fake_connect(_url: str, **_kwargs):
        """
        Return malformed binary frame for decode failure.
        """
        return DummyWebSocket([b"not-a-valid-protobuf"])

    monkeypatch.setattr(state_stream_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr="http://device.local")
    with pytest.raises(exceptions.BusyBarProtocolError):
        async for _ in client.stream_status_ws():
            pass
    await client.aclose()


@pytest.mark.asyncio
async def test_stream_status_ws_cloud_uses_the_cloud_path_and_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Cloud streaming targets /busybar/status/ws and authenticates by header.

    This used to raise NotImplementedError even though the cloud publishes the
    endpoint. The credential also moves: the device takes it as a query
    parameter, the cloud as the same bearer header the REST calls use.
    """
    seen: dict[str, object] = {}

    def fake_connect(uri: str, **kwargs: object) -> object:
        seen["uri"] = uri
        seen["headers"] = kwargs.get("additional_headers")
        raise AssertionError("stop before connecting")

    monkeypatch.setattr(state_stream_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr=None, token="secret")
    with pytest.raises(exceptions.BusyBarWebSocketError):
        async for _ in client.stream_status_ws():
            pass
    await client.aclose()

    assert seen["uri"] == "wss://api.busy.app/busybar/status/ws"
    assert seen["headers"] == {"Authorization": "Bearer secret"}


@pytest.mark.asyncio
async def test_stream_status_ws_device_keeps_the_query_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A local device still receives its access key in the URL.
    """
    seen: dict[str, object] = {}

    def fake_connect(uri: str, **kwargs: object) -> object:
        seen["uri"] = uri
        seen["headers"] = kwargs.get("additional_headers")
        raise AssertionError("stop before connecting")

    monkeypatch.setattr(state_stream_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr="10.0.4.20", token="1234")
    with pytest.raises(exceptions.BusyBarWebSocketError):
        async for _ in client.stream_status_ws():
            pass
    await client.aclose()

    assert seen["uri"] == "ws://10.0.4.20/api/status/ws?x-api-token=1234"
    assert seen["headers"] is None
