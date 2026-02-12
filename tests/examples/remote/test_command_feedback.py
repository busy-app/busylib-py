from __future__ import annotations

import argparse

import pytest

from examples.remote.command_core import CommandArgumentParser, CommandBase, CommandRegistry
from examples.remote.runner import _handle_command_line


class NeedsArgCommand(CommandBase):
    """
    Command that requires a positional argument.
    """

    name = "needs"

    def build_parser(self) -> CommandArgumentParser:
        """
        Build an argument parser that requires a value.
        """
        parser = CommandArgumentParser(prog="needs", add_help=True)
        parser.add_argument("value")
        return parser

    async def run(self, _args: argparse.Namespace) -> None:
        """
        No-op command body used for tests.
        """
        return None


@pytest.mark.asyncio
async def test_unknown_command_reports_status() -> None:
    """
    Emit a status message when the command is unknown.
    """
    registry = CommandRegistry()
    messages: list[str] = []

    await _handle_command_line(
        "unknown",
        command_registry=registry,
        status_message=messages.append,
    )

    assert messages == ["command: Unknown command: unknown"]


@pytest.mark.asyncio
async def test_invalid_args_reports_status() -> None:
    """
    Emit a status message when arguments fail to parse.
    """
    registry = CommandRegistry()
    registry.register_command(NeedsArgCommand())
    messages: list[str] = []

    await _handle_command_line(
        "needs",
        command_registry=registry,
        status_message=messages.append,
    )

    assert messages
    assert messages[0].startswith("command: ")
    assert "required" in messages[0]
