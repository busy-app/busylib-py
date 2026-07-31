"""
Device operations the setup wizard is built from.

Each function does one thing with the client and returns plain data: no
prompting, no printing, no wizard state. That keeps them usable on their own
and makes them the worked examples the documentation quotes, so the guide and
the program can't drift apart.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from busylib import types, versioning
from busylib.client import AsyncBusyBar

logger = logging.getLogger(__name__)

# The device only accepts an install while its own check reports "available";
# any other value means the check is still running or found nothing.
CHECK_STATUS_AVAILABLE = "available"
CHECK_STATUS_TERMINAL_NO_UPDATE = frozenset({"not_available", "failure"})

UPDATE_POLL_INTERVAL_SECONDS = 3.0
UPDATE_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True)
class FirmwareState:
    """
    What the device runs, and whether this library supports it.
    """

    firmware_version: str | None
    api_version: str
    supported: bool


async def read_firmware_state(client: AsyncBusyBar) -> FirmwareState:
    """
    Read the device's API version and the firmware version behind it.

    `/api/version` only reports `api_semver`; the firmware's own version
    string lives under `/api/status`. Reading the second is best-effort, so
    an unreachable status endpoint costs the label rather than the verdict.
    """
    info = await client.version()
    api_version = info.api_semver or "unknown"

    firmware_version = info.version
    if not firmware_version:
        firmware_version = await _firmware_version_from_status(client)

    supported = (
        versioning.compatibility_error(
            library_version=versioning.API_VERSION,
            device_version=api_version,
        )
        is None
    )
    return FirmwareState(
        firmware_version=firmware_version,
        api_version=api_version,
        supported=supported,
    )


async def _firmware_version_from_status(client: AsyncBusyBar) -> str | None:
    """
    Pull the firmware version out of `/api/status`, or None if unreadable.
    """
    try:
        status = await client.status()
    except Exception as exc:  # noqa: BLE001
        logger.debug("setup: could not read firmware version: %s", exc)
        return None
    if status.firmware is not None and status.firmware.version:
        return status.firmware.version
    if status.system is not None and status.system.version:
        return status.system.version
    return None


async def find_available_update(
    client: AsyncBusyBar,
    *,
    timeout: float = UPDATE_TIMEOUT_SECONDS,
    poll_interval: float = UPDATE_POLL_INTERVAL_SECONDS,
) -> str | None:
    """
    Ask the device to check for an update and wait for the verdict.

    Returns the offered version, or None when the check finishes with
    nothing to install. `available_version` alone isn't enough to act on: it
    keeps the version from an earlier check, so the device's current status
    has to read "available" before an install is accepted.
    """
    await client.update_check()

    started = time.monotonic()
    while time.monotonic() - started < timeout:
        status = await client.update_status()
        check = status.check
        if check is not None:
            result = (check.status or "").lower()
            if result == CHECK_STATUS_AVAILABLE and check.available_version:
                return check.available_version
            if result in CHECK_STATUS_TERMINAL_NO_UPDATE:
                return None
        await asyncio.sleep(poll_interval)
    return None


async def install_update(client: AsyncBusyBar, version: str) -> None:
    """
    Start installing a firmware version. The device reboots to apply it.
    """
    await client.update_install(version)


async def read_wifi_state(client: AsyncBusyBar) -> tuple[bool, str]:
    """
    Return whether the device is associated, and a label describing it.
    """
    info = await client.wifi_status()
    if info.state == types.WifiState.CONNECTED:
        return True, info.ssid or "connected"
    return False, str(info.state or "not connected")


async def scan_networks(client: AsyncBusyBar) -> list[types.Network]:
    """
    Scan for nearby networks, returning an empty list if scanning is refused.

    The device cannot scan while associated - it answers 400 "Scan not
    possible when connected" - so callers fall back to entering an SSID.
    """
    try:
        found = await client.wifi_networks()
    except Exception as exc:  # noqa: BLE001
        logger.info("setup: network scan unavailable (%s)", exc)
        return []
    return [n for n in (found.networks or []) if n.ssid]


async def join_network(
    client: AsyncBusyBar,
    ssid: str,
    *,
    password: str | None = None,
    security: types.WifiSecurityMethod | None = None,
) -> None:
    """
    Ask the device to join a network.
    """
    await client.wifi_connect(
        types.ConnectRequestConfig(ssid=ssid, password=password, security=security)
    )


async def read_clock_offset(client: AsyncBusyBar) -> timedelta | None:
    """
    Read the device's UTC offset, or None if its clock can't be parsed.

    The API exposes no timezone name, so the offset is the only value that
    can be compared against this computer.
    """
    info = await client.time()
    if not info.timestamp:
        return None
    try:
        return datetime.fromisoformat(info.timestamp).utcoffset()
    except ValueError:
        return None


async def set_timezone(client: AsyncBusyBar, timezone: str) -> None:
    """
    Set the device timezone to an IANA name such as `Europe/Moscow`.
    """
    await client.time_timezone(timezone)


async def read_device_name(client: AsyncBusyBar) -> str:
    """
    Read the device's current name.
    """
    info = await client.name()
    return info.name or info.device or info.value or ""


async def rename_device(client: AsyncBusyBar, name: str) -> None:
    """
    Rename the device. The name appears on the bar and in discovery.
    """
    await client.name_set(name)


async def read_link_state(client: AsyncBusyBar) -> tuple[bool, str]:
    """
    Return whether the bar is linked to a cloud account, and to whom.
    """
    info = await client.account_info()
    if info.linked:
        return True, info.email or "linked"
    return False, "not linked"


async def request_link_code(client: AsyncBusyBar) -> types.AccountLink:
    """
    Ask the device for a fresh cloud pairing code.
    """
    return await client.account_link()
