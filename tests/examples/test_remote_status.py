from __future__ import annotations

import asyncio

import pytest

from examples.remote import constants as remote_constants
from examples.remote import runner as remote_runner
from busylib import display


class DummyRenderer:
    """
    Minimal renderer stub for status message tests.
    """

    def __init__(self) -> None:
        """
        Initialize without additional state.
        """
        self.frames: list[bytes] = []

    def render(self, frame: bytes) -> None:
        """
        Record rendered frames for assertions.
        """
        self.frames.append(frame)


class DummyClient:
    """
    Minimal WS client stub yielding a single frame.
    """

    def __init__(self, frame: bytes) -> None:
        """
        Store frame bytes for streaming.
        """
        self.base_url = "http://example.local"
        self._frame = frame

    async def stream_screen_ws(self, _display: int):
        """
        Yield a single frame and stop.
        """
        yield self._frame

    async def aclose(self) -> None:
        """
        No-op close for the stub.
        """
        return None


@pytest.mark.asyncio
async def test_stream_ws_emits_status_messages() -> None:
    """
    Ensure status messages are emitted before the first frame renders.
    """
    spec = display.get_display_spec(display.FRONT_DISPLAY)
    frame = bytes(spec.width * spec.height * 3)
    status: list[str] = []

    def status_message(message: str) -> None:
        """
        Capture status messages in a list.
        """
        status.append(message)

    client = DummyClient(frame)
    renderer = DummyRenderer()
    stop_event = asyncio.Event()

    await remote_runner._stream_ws(
        client=client,
        spec=spec,
        stop_event=stop_event,
        renderer=renderer,
        status_message=status_message,
    )

    assert status[:3] == [
        remote_constants.TEXT_INIT_WS,
        remote_constants.TEXT_INIT_WAIT_FRAME,
        remote_constants.TEXT_INIT_STREAMING,
    ]
    assert renderer.frames
