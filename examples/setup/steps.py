"""
The wizard's steps.

Each step is a thin wrapper: it asks `operations` what the device currently
reports, decides whether anything is left to do, and drives the prompts. All
the actual client work lives in `examples.setup.operations`, so a step reads
as the conversation with the user rather than a mix of both.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from busylib import types, versioning
from busylib.client import AsyncBusyBar
from busylib.devices import BUSYBAR_DEFAULT_NAME

from examples.setup import operations
from examples.setup.prompts import Prompt, SetupCancelled
from examples.shared.device_name import validate_device_name
from examples.shared.timezones import resolve_timezone

DEFAULT_DEVICE_NAME = BUSYBAR_DEFAULT_NAME.decode()

CLOUD_DASHBOARD_URL = "https://cloud.busy.app/dashboard"
CLOUD_LINK_POLL_INTERVAL_SECONDS = 3.0
CLOUD_LINK_TIMEOUT_SECONDS = 600.0
# Ask for a new code slightly before the old one lapses, so the user is never
# looking at one that has just gone stale.
CLOUD_CODE_RENEW_MARGIN_SECONDS = 10


@dataclass(frozen=True)
class StepStatus:
    """
    Whether a step still needs doing, plus a short human-readable state.
    """

    done: bool
    summary: str


class SetupStep:
    """
    One configuration step: report its state, then optionally perform it.
    """

    key: str
    title: str

    async def status(self, client: AsyncBusyBar) -> StepStatus:
        """
        Inspect the device to decide whether this step is already done.
        """
        raise NotImplementedError

    async def run(self, client: AsyncBusyBar, prompt: Prompt) -> None:
        """
        Perform the step, prompting the user for anything required.
        """
        raise NotImplementedError


class FirmwareStep(SetupStep):
    """
    Bring the device firmware up to a version this library supports.
    """

    key = "firmware"
    title = "Firmware"

    async def status(self, client: AsyncBusyBar) -> StepStatus:
        """
        Compare the device's API version against the library's target.
        """
        state = await operations.read_firmware_state(client)
        label = (
            f"{state.firmware_version} (API {state.api_version})"
            if state.firmware_version
            else f"API {state.api_version}"
        )
        if state.supported:
            return StepStatus(done=True, summary=f"{label} - supported")
        return StepStatus(
            done=False,
            summary=f"{label} - library targets API {versioning.API_VERSION}",
        )

    async def run(self, client: AsyncBusyBar, prompt: Prompt) -> None:
        """
        Check for an update and install it, waiting for the device to apply it.
        """
        prompt.info("Checking for a firmware update...")
        try:
            available = await operations.find_available_update(client)
        except TimeoutError as exc:
            # Distinct from "nothing to install": the check never finished,
            # so reporting no update would be inventing an answer.
            prompt.info(f"{exc}. Try again, or update from the device UI.")
            return
        if not available:
            prompt.info(
                "No update is offered by the device. If the API version is "
                "still behind, update over USB or from the device UI."
            )
            return

        if not await prompt.confirm(f"Install firmware {available}?"):
            raise SetupCancelled

        prompt.info(f"Installing {available}; the device will reboot when done.")
        await operations.install_update(client, available)
        prompt.info(
            "Update started. Re-run setup once the bar is back online to "
            "confirm the new version."
        )


class WifiStep(SetupStep):
    """
    Join the bar to a Wi-Fi network so it works away from USB.
    """

    key = "wifi"
    title = "Wi-Fi"

    async def status(self, client: AsyncBusyBar) -> StepStatus:
        """
        Report the current Wi-Fi association.
        """
        connected, label = await operations.read_wifi_state(client)
        return StepStatus(done=connected, summary=label)

    async def run(self, client: AsyncBusyBar, prompt: Prompt) -> None:
        """
        Scan for networks, then join the one the user picks.
        """
        prompt.info("Scanning for networks...")
        networks = await operations.scan_networks(client)

        security: types.WifiSecurityMethod | None = None
        if networks:
            labels = [
                f"{n.ssid} ({n.security.value if n.security else 'unknown'})"
                for n in networks
            ]
            labels.append("Enter an SSID manually")
            index = await prompt.choose("Select a network:", labels)
            if index < len(networks):
                chosen = networks[index]
                ssid = chosen.ssid or ""
                security = chosen.security
            else:
                ssid = await prompt.text("SSID")
        else:
            prompt.info("No networks found; the device cannot scan while connected.")
            ssid = await prompt.text("SSID")

        if not ssid:
            raise SetupCancelled

        password: str | None = None
        if security != types.WifiSecurityMethod.OPEN:
            password = await prompt.secret(f"Password for {ssid}") or None

        prompt.info(f"Connecting to {ssid}...")
        await operations.join_network(
            client, ssid, password=password, security=security
        )
        prompt.info(f"Connect request sent for {ssid}.")


class TimezoneStep(SetupStep):
    """
    Align the bar's clock offset with the computer running setup.
    """

    key = "timezone"
    title = "Timezone"

    async def status(self, client: AsyncBusyBar) -> StepStatus:
        """
        Compare the device's UTC offset with this machine's.
        """
        device_offset = await operations.read_clock_offset(client)
        if device_offset is None:
            return StepStatus(done=False, summary="unknown")

        local_offset = datetime.now().astimezone().utcoffset()
        label = _format_offset(device_offset)
        if local_offset is not None and device_offset == local_offset:
            return StepStatus(done=True, summary=f"{label} - matches this computer")
        return StepStatus(
            done=False,
            summary=f"{label} - this computer is {_format_offset(local_offset)}",
        )

    async def run(self, client: AsyncBusyBar, prompt: Prompt) -> None:
        """
        Set the timezone, defaulting to this machine's IANA name.
        """
        value = await prompt.text(
            "Timezone (IANA name, city, or UTC offset)",
            default=_local_timezone_name(),
        )
        resolved, error = resolve_timezone(value)
        if error is not None or resolved is None:
            prompt.info(f"Could not resolve timezone: {error or 'unknown error'}")
            raise SetupCancelled

        await operations.set_timezone(client, resolved)
        prompt.info(f"Timezone set to {resolved}.")


class NameStep(SetupStep):
    """
    Give the bar a recognisable name, used on-device and in discovery.
    """

    key = "name"
    title = "Device name"

    async def status(self, client: AsyncBusyBar) -> StepStatus:
        """
        Treat the factory default name as "not set yet".
        """
        current = await operations.read_device_name(client)
        if current and current != DEFAULT_DEVICE_NAME:
            return StepStatus(done=True, summary=current)
        return StepStatus(done=False, summary=f"{current or 'unset'} (factory default)")

    async def run(self, client: AsyncBusyBar, prompt: Prompt) -> None:
        """
        Validate a new name locally, then apply it.
        """
        value = await prompt.text("Device name")
        error = validate_device_name(value)
        if error is not None:
            prompt.info(f"Invalid name: {error}")
            raise SetupCancelled

        await operations.rename_device(client, value)
        prompt.info(f"Device name set to {value}.")


class CloudStep(SetupStep):
    """
    Link the bar to a BUSY cloud account.
    """

    key = "cloud"
    title = "Cloud account"

    async def status(self, client: AsyncBusyBar) -> StepStatus:
        """
        Report whether the device is already linked.
        """
        linked, label = await operations.read_link_state(client)
        return StepStatus(done=linked, summary=label)

    async def run(self, client: AsyncBusyBar, prompt: Prompt) -> None:
        """
        Show a pairing code and keep it fresh until the bar is linked.

        Codes expire, usually sooner than it takes to find the dashboard and
        sign in, so this polls for the link and fetches a new code whenever
        the current one lapses instead of printing a stale one once. Answer
        "no" at the prompt to skip linking for now.
        """
        prompt.info(f"Link this bar at {CLOUD_DASHBOARD_URL} or in the BUSY App.")
        if not await prompt.confirm("Link it now?", default=True):
            # Skip just this step - the rest of the wizard carries on.
            raise SetupCancelled

        deadline = time.monotonic() + CLOUD_LINK_TIMEOUT_SECONDS
        shown_code: str | None = None
        expires_at: int | None = None

        while time.monotonic() < deadline:
            if shown_code is None or _code_expired(expires_at):
                link = await operations.request_link_code(client)
                if not link.code:
                    prompt.info("The device did not return a linking code.")
                    raise SetupCancelled
                shown_code = link.code
                expires_at = link.expires_at
                prompt.info(f"Code: {shown_code}{_expiry_suffix(expires_at)}")

            await asyncio.sleep(CLOUD_LINK_POLL_INTERVAL_SECONDS)

            linked, label = await operations.read_link_state(client)
            if linked:
                prompt.info(f"Linked to {label}.")
                return

        prompt.info("Gave up waiting for the bar to be linked.")
        raise SetupCancelled


def default_steps() -> list[SetupStep]:
    """
    Return the setup steps in the order a new owner should do them.
    """
    return [FirmwareStep(), WifiStep(), TimezoneStep(), NameStep(), CloudStep()]


def _code_expired(expires_at: int | None) -> bool:
    """
    Whether a pairing code is at or near its expiry.
    """
    if expires_at is None:
        return False
    return time.time() >= expires_at - CLOUD_CODE_RENEW_MARGIN_SECONDS


def _expiry_suffix(expires_at: int | None) -> str:
    """
    Render the expiry as local time rather than a raw unix timestamp.
    """
    if expires_at is None:
        return ""
    local = datetime.fromtimestamp(expires_at).astimezone()
    return f" (valid until {local:%H:%M:%S})"


def _format_offset(offset: timedelta | None) -> str:
    """
    Render a UTC offset as `UTC+HH:MM`.
    """
    if offset is None:
        return "unknown"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _local_timezone_name() -> str | None:
    """
    Best-effort IANA name for this machine, or None if it can't be determined.

    Falls back to `_whole_hour_offset_label`, which declines to guess when
    the offset has minutes.
    """
    local = datetime.now().astimezone()

    key = getattr(local.tzinfo, "key", None)
    if isinstance(key, str) and key:
        return key

    name = local.tzname()
    if name and "/" in name:
        return name

    try:
        resolved = Path("/etc/localtime").resolve()
        parts = resolved.parts
        if "zoneinfo" in parts:
            return "/".join(parts[parts.index("zoneinfo") + 1 :])
    except OSError:
        pass

    return _whole_hour_offset_label(local.utcoffset() or timedelta(0))


def _whole_hour_offset_label(offset: timedelta) -> str | None:
    """
    Render a UTC offset as a `resolve_timezone`-compatible label.

    Returns None when the offset has minutes, because `resolve_timezone`
    rejects those - suggesting "+5" to somebody in +05:30 would be worse
    than suggesting nothing at all.
    """
    total_minutes = int(offset.total_seconds() // 60)
    if total_minutes % 60:
        return None
    hours = total_minutes // 60
    return f"{'+' if hours >= 0 else ''}{hours}"
