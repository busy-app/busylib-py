from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Callable
from zoneinfo import available_timezones

from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase

logger = logging.getLogger(__name__)

_OFFSET_RE = re.compile(
    r"^(?:utc|gmt)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$",
    flags=re.IGNORECASE,
)


def resolve_timezone(
    value: str,
    timezones: set[str] | None = None,
) -> tuple[str | None, str | None]:
    """
    Resolve a timezone label to an IANA timezone name.

    Supports numeric offsets like "+3" and city names like "Moscow".
    """
    normalized = value.strip()
    if not normalized:
        return None, "timezone value is empty"

    normalized = normalized.replace(" ", "_")
    known_timezones = timezones or available_timezones()

    offset_tz, offset_error = _resolve_offset(normalized, known_timezones)
    if offset_error is not None:
        return None, offset_error
    if offset_tz is not None:
        return offset_tz, None

    direct_match = _match_direct_timezone(normalized, known_timezones)
    if direct_match is not None:
        return direct_match, None

    short_match, short_error = _match_short_timezone(normalized, known_timezones)
    if short_error is not None:
        return None, short_error
    if short_match is not None:
        return short_match, None

    return None, f"unknown timezone '{value}'"


def _resolve_offset(
    value: str,
    timezones: set[str],
) -> tuple[str | None, str | None]:
    """
    Resolve numeric offsets to an Etc/GMT timezone when possible.
    """
    match = _OFFSET_RE.match(value)
    if match is None:
        return None, None

    sign, hours_str, minutes_str = match.groups()
    hours = int(hours_str)
    minutes = int(minutes_str or 0)

    if hours > 14 or minutes >= 60 or (hours == 14 and minutes > 0):
        return None, "timezone offset is out of range"

    if minutes != 0:
        return None, "offset minutes are not supported; use an IANA name"

    if hours == 0 and minutes == 0:
        tz_name = "Etc/UTC"
    else:
        tz_sign = "-" if sign == "+" else "+"
        tz_name = f"Etc/GMT{tz_sign}{hours}"

    if tz_name not in timezones:
        return None, f"timezone '{tz_name}' is not available"

    return tz_name, None


def _match_direct_timezone(
    value: str,
    timezones: set[str],
) -> str | None:
    """
    Match a full IANA timezone name with case-insensitive fallback.
    """
    if value in timezones:
        return value

    lowered = value.lower()
    matches = [
        tz
        for tz in timezones
        if tz.lower() == lowered
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _match_short_timezone(
    value: str,
    timezones: set[str],
) -> tuple[str | None, str | None]:
    """
    Match a city-only value against available timezones.
    """
    if "/" in value:
        return None, None

    lowered = value.lower()
    matches = [
        tz
        for tz in timezones
        if tz.rsplit("/", 1)[-1].lower() == lowered
    ]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        sample = ", ".join(sorted(matches)[:3])
        return None, f"ambiguous timezone '{value}': {sample}"
    return None, None


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
            await self._client.set_time_timezone(timezone)
        except Exception as exc:  # noqa: BLE001
            logger.exception("command:timezone_set failed")
            self._status_message(f"timezone_set: error {exc}")
            return
        self._status_message(f"timezone_set: ok {timezone}")
