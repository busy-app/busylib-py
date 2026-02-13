from __future__ import annotations

import argparse
import asyncio
import logging

from busylib.client import AsyncBusyBar
from busylib import types

from examples.remote.command_core import CommandArgumentParser, CommandBase

logger = logging.getLogger(__name__)


class ClockCommand(CommandBase):
    """
    Open the clock app via input key sequence.
    """

    name = "clock"

    def __init__(self, client: AsyncBusyBar) -> None:
        """
        Store the client used to send input keys.
        """
        self._client = client

    @classmethod
    def build(cls, **deps: object) -> ClockCommand | None:
        """
        Build the command if the BusyBar client is available.
        """
        client = deps.get("client")
        if isinstance(client, AsyncBusyBar):
            return cls(client)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the clock command.
        """
        return CommandArgumentParser(prog="clock", add_help=False)

    async def run(self, _args: argparse.Namespace) -> None:
        """
        Trigger the clock app sequence.
        """
        logger.info("command:clock")
        await self._client.send_input_key(types.InputKey.APPS)
        await asyncio.sleep(0.2)
        await self._client.send_input_key(types.InputKey.OK)
        await asyncio.sleep(0.2)
        await self._client.send_input_key(types.InputKey.OK)
