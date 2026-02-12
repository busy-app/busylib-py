from __future__ import annotations

import asyncio

from busylib.client import AsyncBusyBar

from examples.remote.commands import InputCapture, discover_commands


def test_discover_commands_builds_instances() -> None:
    """
    Ensure autodiscovery returns all command instances with dependencies.
    """
    client = AsyncBusyBar(addr="http://example.com")
    input_capture = InputCapture()
    stop_event = asyncio.Event()

    commands = discover_commands(
        client=client,
        status_message=lambda _message: None,
        stop_event=stop_event,
        input_capture=input_capture,
    )

    names = {command.name for command in commands}
    assert names == {
        "audio",
        "clear",
        "clock",
        "quit",
        "record_audio",
        "text",
        "timezone_set",
    }
