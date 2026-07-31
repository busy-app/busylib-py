from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase
from examples.shared.timezones import resolve_timezone

logger = logging.getLogger(__name__)


class TimezoneSetCommand(CommandBase):
    """
    Resolve a timezone label and set it on the device.
    """

    name = "timezone_set"
    aliases = ("tz",)

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
    def build(cls, **deps: object) -> TimezoneSetCommand | None:
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
        Build the argument parser for the timezone set command.
        """
        parser = CommandArgumentParser(prog="timezone_set", add_help=True)
        parser.add_argument(
            "timezone",
            nargs="+",
            help="Timezone label (e.g. +3, Europe/Moscow, Moscow)",
        )
        return parser

    async def run(self, args: argparse.Namespace) -> None:
        """
        Resolve the timezone and send it to the device API.
        """
        raw_value = " ".join(args.timezone).strip()
        logger.info("command:timezone_set value=%s", raw_value)
        timezone, error = resolve_timezone(raw_value)
        if error is not None or timezone is None:
            message = error or "failed to resolve timezone"
            self._status_message(f"timezone_set: error {message}")
            return

        self._status_message(f"timezone_set: setting {timezone}")
        try:
            await self._client.time_timezone(timezone)
        except Exception as exc:  # noqa: BLE001
            logger.exception("command:timezone_set failed")
            self._status_message(f"timezone_set: error {exc}")
            return
        self._status_message(f"timezone_set: ok {timezone}")
