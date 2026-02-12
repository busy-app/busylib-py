from __future__ import annotations

import argparse
import logging

from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase

logger = logging.getLogger(__name__)


class ClearCommand(CommandBase):
    """
    Clear the remote display on demand.
    """

    name = "clear"
    aliases = ("c",)

    def __init__(self, client: AsyncBusyBar) -> None:
        """
        Store the client used to clear the display.
        """
        self._client = client

    @classmethod
    def build(cls, **deps: object) -> ClearCommand | None:
        """
        Build the command if the BusyBar client is available.
        """
        client = deps.get("client")
        if isinstance(client, AsyncBusyBar):
            return cls(client)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the clear command.
        """
        return CommandArgumentParser(prog="clear", add_help=False)

    async def run(self, _args: argparse.Namespace) -> None:
        """
        Clear the remote display.
        """
        logger.info("command:clear")
        await self._client.clear_display()
