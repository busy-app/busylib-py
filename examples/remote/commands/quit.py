from __future__ import annotations

import argparse
import asyncio
import logging

from examples.remote.command_core import CommandArgumentParser, CommandBase

logger = logging.getLogger(__name__)


class QuitCommand(CommandBase):
    """
    Stop the remote loop.
    """

    name = "quit"
    aliases = ("q", "exit")

    def __init__(self, stop_event: asyncio.Event) -> None:
        """
        Store the stop event to signal shutdown.
        """
        self._stop_event = stop_event

    @classmethod
    def build(cls, **deps: object) -> QuitCommand | None:
        """
        Build the command if the stop event is available.
        """
        stop_event = deps.get("stop_event")
        if isinstance(stop_event, asyncio.Event):
            return cls(stop_event)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for quit.
        """
        return CommandArgumentParser(prog="q", add_help=False)

    async def run(self, _args: argparse.Namespace) -> None:
        """
        Signal the remote loop to stop.
        """
        logger.info("command:quit")
        self._stop_event.set()
