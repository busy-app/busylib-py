from __future__ import annotations

import argparse
import asyncio

import pytest

from examples.remote import main as remote_main
from examples.remote import runner as remote_runner


def test_cloud_forces_http_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure cloud mode switches to polling with 1 fps.

    This keeps streaming compatible with cloud proxies.
    """

    class DummyCloudClient:
        """
        Minimal client stub marked as cloud mode.
        """

        def __init__(self) -> None:
            """
            Initialize cloud properties required by the runner.
            """
            self.is_cloud = True
            self.base_url = "https://proxy.dev.busy.app"

        async def aclose(self) -> None:
            """
            Async no-op close used by the runner cleanup.
            """
            return None

    async def fake_poll_http(**kwargs) -> None:
        """
        Capture polling interval and stop the loop.
        """
        kwargs["stop_event"].set()
        captured["interval"] = kwargs["interval"]

    async def forbidden_stream_ws(**_kwargs) -> None:
        """
        Guard against WebSocket streaming in cloud mode.
        """
        raise AssertionError("WebSocket streaming should be disabled in cloud mode.")

    captured: dict[str, float] = {}

    monkeypatch.setattr(remote_runner, "_build_client", lambda *_: DummyCloudClient())
    monkeypatch.setattr(remote_runner, "_poll_http", fake_poll_http)
    monkeypatch.setattr(remote_runner, "_stream_ws", forbidden_stream_ws)
    monkeypatch.setattr(
        remote_runner,
        "build_periodic_tasks",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(remote_main, "_clear_terminal", lambda: None)

    args = argparse.Namespace(
        addr=None,
        token="token",
        http_poll_interval=None,
        spacer=" ",
        pixel_char=remote_main.PIXEL_CHAR,
        log_level="INFO",
        log_file=None,
        no_send_input=True,
        keymap_file=None,
    )

    asyncio.run(remote_main._run(args))

    assert captured["interval"] == 1.0
