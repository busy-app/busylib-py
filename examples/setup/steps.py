from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from busylib import types, versioning
from busylib.client import AsyncBusyBar
from busylib.devices import BUSYBAR_DEFAULT_NAME

from examples.setup.prompts import Prompt, SetupCancelled
from examples.shared.device_name import validate_device_name
from examples.shared.timezones import resolve_timezone

# Factory bars ship on firmware 1.0.2, which serves API 24.3.0 while this
# library targets 25.0.0. Updating is therefore the first thing a new owner
# needs, and every other step reads better once it's out of the way.
UPDATE_POLL_INTERVAL_SECONDS = 3.0
UPDATE_TIMEOUT_SECONDS = 600.0

# `check.status` values that mean the check finished without an update. Any
# other value (notably "none") means it is still running.
CLOUD_DASHBOARD_URL = "https://cloud.busy.app/dashboard"
CLOUD_LINK_POLL_INTERVAL_SECONDS = 3.0
CLOUD_LINK_TIMEOUT_SECONDS = 600.0
# Ask for a new code slightly before the old one lapses, so the user is never
# looking at one that has just gone stale.
CLOUD_CODE_RENEW_MARGIN_SECONDS = 10

CHECK_STATUS_AVAILABLE = "available"
CHECK_STATUS_TERMINAL_NO_UPDATE = frozenset({"not_available", "failure"})
DEFAULT_DEVICE_NAME = BUSYBAR_DEFAULT_NAME.decode()

logger = logging.getLogger(__name__)


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

        `/api/version` only ever reports `api_semver` - the firmware's own
        version string lives under `/api/status` in the `firmware` section -
        so the two are read separately. The status call is best-effort: an
        unreachable or unauthorised endpoint costs the version label, not
        the compatibility verdict.
        """
        info = await client.version()
        device_api = info.api_semver or "unknown"
        error = versioning.compatibility_error(
            library_version=versioning.API_VERSION,
            device_version=device_api,
        )

        firmware_version = info.version or await self._firmware_version(client)
        summary = (
            f"{firmware_version} (API {device_api})"
            if firmware_version
            else f"API {device_api}"
        )
        if error is None:
            return StepStatus(done=True, summary=f"{summary} - supported")
        return StepStatus(
            done=False,
            summary=f"{summary} - library targets API {versioning.API_VERSION}",
        )

    @staticmethod
    async def _firmware_version(client: AsyncBusyBar) -> str | None:
        """
        Read the firmware version from `/api/status`, or None if unavailable.
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

    async def run(self, client: AsyncBusyBar, prompt: Prompt) -> None:
        """
        Check for an update and install it, waiting for the device to apply it.
        """
        prompt.info("Checking for a firmware update...")
        await client.update_check()
        available = await self._await_check_result(client)
        if not available:
            prompt.info(
                "No update is offered by the device. If the API version is "
                "still behind, update over USB or from the device UI."
            )
            return

        if not await prompt.confirm(f"Install firmware {available}?"):
            raise SetupCancelled

        prompt.info(f"Installing {available}; the device will reboot when done.")
        await client.update_install(available)
        prompt.info(
            "Update started. Re-run setup once the bar is back online to "
            "confirm the new version."
        )

    async def _await_check_result(self, client: AsyncBusyBar) -> str | None:
        """
        Poll update status until the check reports a version or finishes.

        The device reports `check.status` as one of `available`,
        `not_available`, `failure`, or `none`, and `check.event` as `start`,
        `stop`, or `none`. Only the first two statuses are terminal: `none`
        means the check hasn't produced a result yet, so polling has to
        continue rather than concluding there's no update.
        """
        # Measure real elapsed time: counting only the sleeps ignored how
        # long update_status() itself took, so the effective timeout drifted
        # well past UPDATE_TIMEOUT_SECONDS.
        started = time.monotonic()
        while time.monotonic() - started < UPDATE_TIMEOUT_SECONDS:
            status = await client.update_status()
            check = status.check
            if check is not None:
                result = (check.status or "").lower()
                # The device only accepts an install while its own check
                # state says "available". `available_version` alone isn't
                # enough: it keeps the version from an earlier check, so
                # acting on it mid-check gets a 400 "Update not available".
                if result == CHECK_STATUS_AVAILABLE and check.available_version:
                    return check.available_version
                if result in CHECK_STATUS_TERMINAL_NO_UPDATE:
                    return None
            await asyncio.sleep(UPDATE_POLL_INTERVAL_SECONDS)
        return None


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
        info = await client.wifi_status()
        if info.state == types.WifiState.CONNECTED:
            return StepStatus(done=True, summary=info.ssid or "connected")
        return StepStatus(done=False, summary=str(info.state or "not connected"))

    async def run(self, client: AsyncBusyBar, prompt: Prompt) -> None:
        """
        Scan for networks, then join the one the user picks.
        """
        prompt.info("Scanning for networks...")
        try:
            found = await client.wifi_networks()
            networks = [n for n in (found.networks or []) if n.ssid]
        except Exception as exc:  # noqa: BLE001
            # The device refuses to scan while associated, answering
            # 400 "Scan not possible when connected" - which is exactly the
            # case when this step is re-run with --redo. Fall back to typing
            # the SSID rather than failing the step.
            logger.info("setup: network scan unavailable (%s)", exc)
            prompt.info(f"Could not scan for networks: {exc}")
            networks = []

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
                ssid, security = await prompt.text("SSID"), None
        else:
            prompt.info("No networks found in the scan.")
            ssid, security = await prompt.text("SSID"), None

        if not ssid:
            raise SetupCancelled

        password: str | None = None
        if security != types.WifiSecurityMethod.OPEN:
            password = await prompt.secret(f"Password for {ssid}") or None

        prompt.info(f"Connecting to {ssid}...")
        config = types.ConnectRequestConfig(
            ssid=ssid,
            password=password,
            security=security,
        )
        await client.wifi_connect(config)
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

        There's no timezone-name getter in the API, so the offset is the only
        thing that can be compared; a match is treated as "already set".
        """
        info = await client.time()
        device_offset = _parse_offset(info.timestamp)
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
        default = _local_timezone_name()
        value = await prompt.text(
            "Timezone (IANA name, city, or UTC offset)",
            default=default,
        )
        resolved, error = resolve_timezone(value)
        if error is not None or resolved is None:
            prompt.info(f"Could not resolve timezone: {error or 'unknown error'}")
            raise SetupCancelled

        await client.time_timezone(resolved)
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
        info = await client.name()
        current = info.name or info.device or info.value or ""
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

        await client.name_set(value)
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
        info = await client.account_info()
        if info.linked:
            return StepStatus(done=True, summary=info.email or "linked")
        return StepStatus(done=False, summary="not linked")

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
                link = await client.account_link()
                if not link.code:
                    prompt.info("The device did not return a linking code.")
                    raise SetupCancelled
                shown_code = link.code
                expires_at = link.expires_at
                prompt.info(f"Code: {shown_code}{_expiry_suffix(expires_at)}")

            await asyncio.sleep(CLOUD_LINK_POLL_INTERVAL_SECONDS)

            info = await client.account_info()
            if info.linked:
                prompt.info(f"Linked to {info.email or 'your account'}.")
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


def _parse_offset(timestamp: str | None) -> timedelta | None:
    """
    Extract the UTC offset from an ISO-8601 timestamp.
    """
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    return parsed.utcoffset()


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
