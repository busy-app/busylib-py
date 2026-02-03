from __future__ import annotations

from pathlib import Path

import pytest

from examples.remote.commands import CommandInput, CommandRegistry


@pytest.mark.asyncio
async def test_command_registry_dispatches_args() -> None:
    """
    Ensure the registry splits command line into command and arguments.
    """
    received: list[list[str]] = []
    registry = CommandRegistry()

    def handler(args: list[str]) -> None:
        received.append(args)

    registry.register("ping", handler)
    handled = await registry.handle("ping one two")

    assert handled is True
    assert received == [["one", "two"]]


@pytest.mark.asyncio
async def test_command_registry_handles_quotes() -> None:
    """
    Ensure quoted arguments are preserved by the splitter.
    """
    received: list[list[str]] = []
    registry = CommandRegistry()

    def handler(args: list[str]) -> None:
        received.append(args)

    registry.register("say", handler)
    handled = await registry.handle('say "hello world"')

    assert handled is True
    assert received == [["hello world"]]


@pytest.mark.asyncio
async def test_command_registry_unknown_returns_false() -> None:
    """
    Return False when no handler exists for a command.
    """
    registry = CommandRegistry()
    handled = await registry.handle("missing arg")
    assert handled is False


def test_command_input_history_navigation(tmp_path: Path) -> None:
    """
    Ensure history is recorded and navigated via arrow keys.
    """
    command_input = CommandInput(tmp_path / "history.log")

    command_input.begin()
    events = command_input.feed(b"first")
    assert events[-1] == ("update", ("first", 5))
    events = command_input.feed(b"\r")
    assert events == [("submit", "first")]
    assert command_input.buffer == ""

    command_input.begin()
    events = command_input.feed(b"second")
    assert events[-1] == ("update", ("second", 6))
    events = command_input.feed(b"\r")
    assert events == [("submit", "second")]
    assert command_input.buffer == ""

    command_input.begin()
    events = command_input.feed(b"\x1b[A")
    assert events == [("update", ("second", 6))]
    events = command_input.feed(b"\x1b[A")
    assert events == [("update", ("first", 5))]
    events = command_input.feed(b"\x1b[B")
    assert events == [("update", ("second", 6))]
    events = command_input.feed(b"\x1b[B")
    assert events == [("update", ("", 0))]


def test_command_input_loads_history_file(tmp_path: Path) -> None:
    """
    Ensure history is loaded from the local history file on init.
    """
    path = tmp_path / "history.log"
    path.write_text("one\ntwo\n", encoding="utf-8")
    command_input = CommandInput(path)
    command_input.begin()
    events = command_input.feed(b"\x1b[A")
    assert events == [("update", ("two", 3))]


def test_command_input_moves_cursor_left_right(tmp_path: Path) -> None:
    """
    Ensure left/right arrows move the cursor and insert at position.
    """
    command_input = CommandInput(tmp_path / "history.log")
    command_input.begin()
    command_input.feed(b"ab")
    events = command_input.feed(b"\x1b[D")
    assert events == [("update", ("ab", 1))]
    events = command_input.feed(b"c")
    assert events == [("update", ("acb", 2))]
