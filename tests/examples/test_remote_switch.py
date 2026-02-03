from __future__ import annotations

import argparse
import importlib

import pytest

from busylib import display
from examples.remote.keymap import default_keymap
from examples.remote import runner as remote_runner


class DummyClient:
    """
    Minimal client stub for switch display tests.
    """

    def __init__(self) -> None:
        """
        Store a base URL for logging consistency.
        """
        self.base_url = "http://example.local"

    async def aclose(self) -> None:
        """
        No-op close hook for cleanup paths.
        """
        return None


@pytest.mark.asyncio
async def test_run_switches_display_without_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure Tab/Ctrl+R triggers display switch and keeps the loop running.
    """
    remote_main = importlib.import_module("examples.remote.main")
    spec_sizes: list[tuple[int, int]] = []
    switches = 0

    async def fake_stream_ws(
        *,
        client,
        spec,
        stop_event,
        renderer,
        status_message,
    ) -> None:
        """
        Record the spec size and wait for the stop event.

        This keeps the stream task alive until the switch is triggered.
        """
        spec_sizes.append((spec.width, spec.height))
        await stop_event.wait()

    async def fake_forward_keys(
        *,
        client,
        keymap,
        stop_event,
        renderer=None,
        on_switch=None,
    ) -> None:
        """
        Trigger a single switch and then stop the input task.

        The second invocation only stops the loop without switching again.
        """
        nonlocal switches
        if switches == 0:
            switches += 1
            if on_switch:
                on_switch()
        stop_event.set()

    monkeypatch.setattr(remote_runner, "_build_client", lambda *_: DummyClient())
    monkeypatch.setattr(remote_runner, "_stream_ws", fake_stream_ws)
    monkeypatch.setattr(remote_runner, "_forward_keys", fake_forward_keys)
    monkeypatch.setattr(
        remote_runner,
        "build_periodic_tasks",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(remote_runner, "load_keymap", lambda *_: default_keymap())

    args = argparse.Namespace(
        addr="http://10.0.4.20",
        token=None,
        http_poll_interval=None,
        spacer=" ",
        pixel_char=remote_main.PIXEL_CHAR,
        log_level="INFO",
        log_file=None,
        no_send_input=False,
        keymap_file=None,
    )

    await remote_runner._run(
        args,
        icons=remote_main.ICONS,
        clear_screen=lambda *_args, **_kwargs: None,
        clear_terminal=lambda: None,
        status_message=lambda *_args, **_kwargs: None,
    )

    assert spec_sizes == [
        (display.FRONT_DISPLAY.width, display.FRONT_DISPLAY.height),
        (display.BACK_DISPLAY.width, display.BACK_DISPLAY.height),
    ]
