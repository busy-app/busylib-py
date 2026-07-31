from __future__ import annotations

import re
from zoneinfo import available_timezones


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
    matches = [tz for tz in timezones if tz.lower() == lowered]
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
    matches = [tz for tz in timezones if tz.rsplit("/", 1)[-1].lower() == lowered]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        sample = ", ".join(sorted(matches)[:3])
        return None, f"ambiguous timezone '{value}': {sample}"
    return None, None
