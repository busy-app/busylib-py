import pytest

from busylib import AsyncBusyBar, exceptions
from busylib.client import display as display_client


class DummyWebSocket:
    """
    Minimal async websocket stub for testing connect parameters.

    It records payloads sent by the client and yields no frames.
    """

    def __init__(self) -> None:
        """
        Initialize the stub with an empty send log.
        """
        self.sent: list[str] = []

    async def __aenter__(self) -> "DummyWebSocket":
        """
        Enter the async context for the websocket.

        Returns self to mimic websockets.connect behavior.
        """
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        """
        Exit the async context without suppressing exceptions.

        Always returns False to propagate errors.
        """
        return False

    async def send(self, payload: str) -> None:
        """
        Record a sent payload.

        The payload is stored as a raw JSON string.
        """
        self.sent.append(payload)

    def __aiter__(self):
        """
        Provide an empty async iterator for frames.

        The iterator completes immediately to end the stream.
        """

        async def _iter():
            """
            Yield no frames for the dummy websocket.

            This keeps the stream loop finite in tests.
            """
            if False:
                yield b""

        return _iter()


@pytest.mark.asyncio
async def test_stream_screen_ws_uses_query_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure WS token is sent via query string for the upgrade.

    The connect URL should include x-api-token in its query.
    """
    captured: dict[str, object] = {}

    def fake_connect(url: str, **kwargs):
        """
        Capture the WS URL and headers passed into the connector.

        Returns a dummy websocket to terminate the stream.
        """
        captured["url"] = url
        captured["headers"] = kwargs.get("additional_headers")
        captured["extra"] = kwargs
        return DummyWebSocket()

    monkeypatch.setattr(display_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr="http://device.local", token="secret")
    client.client.headers["Connection"] = "keep-alive"
    async for _frame in client.stream_screen_ws(0):
        pass
    await client.aclose()

    url = captured.get("url")
    extra = captured.get("extra")

    assert isinstance(url, str)
    assert "x-api-token=secret" in url
    assert captured.get("headers") is None
    assert isinstance(extra, dict)
    assert extra.get("compression") is None
    assert "user_agent_header" not in extra
    assert extra.get("max_size") is None
    assert extra.get("ping_interval") is None


@pytest.mark.asyncio
async def test_stream_screen_ws_wraps_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure websocket transport errors are wrapped into domain exceptions.
    """

    def fake_connect(_url: str, **_kwargs):
        raise RuntimeError("ws boom")

    monkeypatch.setattr(display_client.websockets, "connect", fake_connect)

    client = AsyncBusyBar(addr="http://device.local", token="secret")
    with pytest.raises(exceptions.BusyBarWebSocketError) as exc:
        async for _frame in client.stream_screen_ws(0):
            pass
    await client.aclose()

    assert exc.value.path == "/api/screen/ws"
    assert isinstance(exc.value.__cause__, RuntimeError)
