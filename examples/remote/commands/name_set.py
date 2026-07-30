from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase

logger = logging.getLogger(__name__)

# Mirrors the firmware's own rules in
# `applications/services/device_name/device_name.c` so invalid names are
# rejected locally with a clear reason instead of an opaque API error.
MAX_NAME_LENGTH = 20
ALLOWED_SPECIAL_CHARS = " !()-_=+;:,.?'|@#$%^&*[]{}/\\\"<>"


def _is_valid_char(char: str) -> bool:
    """
    Check one character against the firmware's allowed set.

    The firmware accepts ASCII alphanumerics plus a fixed punctuation set,
    and rejects anything non-ASCII, so `isascii()` must be checked before
    `isalnum()` (which is true for non-ASCII letters in Python).
    """
    return char.isascii() and (char.isalnum() or char in ALLOWED_SPECIAL_CHARS)


def validate_device_name(name: str) -> str | None:
    """
    Validate a device name, returning an error message or None if valid.

    Checks run in the same order as the firmware's `device_name_validate()`
    so the reported reason matches what the device itself would report.
    """
    if not name:
        return "name is empty"

    for char in name:
        if not _is_valid_char(char):
            return f"illegal character {char!r}"

    if all(char == " " for char in name):
        return "name consists only of spaces"

    if len(name) > MAX_NAME_LENGTH:
        return f"name is longer than {MAX_NAME_LENGTH} characters"

    return None


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
