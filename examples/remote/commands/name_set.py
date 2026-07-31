from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase
from examples.shared.device_name import MAX_NAME_LENGTH, validate_device_name

logger = logging.getLogger(__name__)


class NameSetCommand(CommandBase):
    """
    Set the device name shown on the bar and in discovery.
    """

    name = "name_set"
    aliases = ("rename",)

    def __init__(
        self,
        client: AsyncBusyBar,
        status_message: Callable[[str], None],
    ) -> None:
        """
        Store the client and status callback for updates.
        """
        self._client = client
        self._status_message = status_message

    @classmethod
    def build(cls, **deps: object) -> NameSetCommand | None:
        """
        Build the command when dependencies are provided.
        """
        client = deps.get("client")
        status_message = deps.get("status_message")
        if isinstance(client, AsyncBusyBar) and callable(status_message):
            return cls(client, status_message)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the name set command.
        """
        parser = CommandArgumentParser(prog="name_set", add_help=True)
        parser.add_argument(
            "name",
            nargs="+",
            help=f'Device name, max {MAX_NAME_LENGTH} chars (e.g. "Front desk")',
        )
        return parser

    async def run(self, args: argparse.Namespace) -> None:
        """
        Validate the requested name and send it to the device API.
        """
        new_name = " ".join(args.name).strip()
        logger.info("command:name_set value=%s", new_name)

        error = validate_device_name(new_name)
        if error is not None:
            self._status_message(f"name_set: error {error}")
            return

        self._status_message(f"name_set: setting {new_name}")
        try:
            await self._client.name_set(new_name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("command:name_set failed")
            self._status_message(f"name_set: error {exc}")
            return
        self._status_message(f"name_set: ok {new_name}")
