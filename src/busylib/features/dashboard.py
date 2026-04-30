from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, Field

from busylib import types
from busylib.client import AsyncBusyBar

logger = logging.getLogger(__name__)


class DeviceSnapshot(BaseModel):
    name: str | None = None
    version: types.VersionInfo | None = None
    status: types.Status | None = None
    system: types.StatusSystem | None = None
    power: types.StatusPower | None = None
    time: datetime | None = None
    wifi: types.StatusResponse | None = None
    brightness: types.DisplayBrightnessInfo | None = None
    volume: types.AudioVolumeInfo | None = None
    ble: types.BleStatus | None = None
    storage: types.StorageStatus | None = None
    field_errors: dict[str, str] = Field(default_factory=dict)
    raw_time: object | None = Field(default=None, exclude=True)

    model_config = {"extra": "ignore"}


async def _safe(
    field_name: str,
    call: Awaitable[object] | object,
) -> tuple[object | None, str | None]:
    """
    Execute field collection and preserve failure details.

    Returns a tuple of parsed value and optional error string so snapshot
    collection can stay partially successful while exposing diagnostics.
    """
    try:
        value = await call if asyncio.iscoroutine(call) else call
        return value, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Snapshot field %s failed: %s", field_name, exc)
        return None, f"{exc.__class__.__name__}: {exc}"


_T = TypeVar("_T")


def _as_type(value: object | None, expected: type[_T]) -> _T | None:
    """
    Narrow a snapshot value to the expected type.

    This keeps pyright happy while preserving runtime safety.
    """
    if isinstance(value, expected):
        return value
    return None


async def collect_device_snapshot(client: AsyncBusyBar) -> DeviceSnapshot:
    """
    Collect a best-effort device snapshot with per-field diagnostics.

    Each field request runs independently. Failed fields are set to None and
    reported in `field_errors` without aborting the whole snapshot.
    """
    tasks = {
        "name": asyncio.create_task(_safe("name", client.get_device_name())),
        "version": asyncio.create_task(_safe("version", client.get_version())),
        "status": asyncio.create_task(_safe("status", client.get_status())),
        "system": asyncio.create_task(_safe("system", client.get_system_status())),
        "power": asyncio.create_task(_safe("power", client.get_power_status())),
        "time": asyncio.create_task(_safe("time", client.get_device_time())),
        "wifi": asyncio.create_task(_safe("wifi", client.get_wifi_status())),
        "brightness": asyncio.create_task(
            _safe("brightness", client.get_display_brightness())
        ),
        "volume": asyncio.create_task(_safe("volume", client.get_audio_volume())),
        "ble": asyncio.create_task(_safe("ble", client.ble_status())),
        "storage": asyncio.create_task(_safe("storage", client.get_storage_status())),
    }

    results: dict[str, object | None] = {}
    field_errors: dict[str, str] = {}
    for key, task in tasks.items():
        value, error = await task
        results[key] = value
        if error:
            field_errors[key] = error

    name = None
    name_payload = results.get("name")
    if isinstance(name_payload, types.DeviceNameResponse):
        name = name_payload.name or name_payload.device or name_payload.value
    elif isinstance(name_payload, dict):
        name = (
            name_payload.get("name")
            or name_payload.get("device")
            or name_payload.get("value")
        )

    parsed_time = None
    raw_time = results.get("time")
    iso_val = None
    if isinstance(raw_time, types.DeviceTimeResponse):
        iso_val = raw_time.timestamp
    elif isinstance(raw_time, dict):
        iso_val = raw_time.get("timestamp")
    if isinstance(iso_val, str):
        try:
            parsed_time = datetime.fromisoformat(iso_val)
        except ValueError:
            parsed_time = None

    return DeviceSnapshot(
        name=name,
        version=_as_type(results.get("version"), types.VersionInfo),
        status=_as_type(results.get("status"), types.Status),
        system=_as_type(results.get("system"), types.StatusSystem),
        power=_as_type(results.get("power"), types.StatusPower),
        time=parsed_time,
        wifi=_as_type(results.get("wifi"), types.StatusResponse),
        brightness=_as_type(results.get("brightness"), types.DisplayBrightnessInfo),
        volume=_as_type(results.get("volume"), types.AudioVolumeInfo),
        ble=_as_type(results.get("ble"), types.BleStatus),
        storage=_as_type(results.get("storage"), types.StorageStatus),
        field_errors=field_errors,
        raw_time=raw_time,
    )


def apply_state_stream_update(
    snapshot: DeviceSnapshot,
    state_message: dict[str, object],
) -> DeviceSnapshot:
    """
    Apply one protobuf `/api/status/ws` state message to an existing snapshot.

    The function updates only fields present in state updates and preserves
    all previously known values for absent fields.
    """
    next_snapshot = snapshot.model_copy(deep=True)
    updates = state_message.get("updates")
    if not isinstance(updates, list):
        return next_snapshot

    for update in updates:
        if not isinstance(update, dict):
            continue

        device_name = update.get("device_name")
        if isinstance(device_name, dict):
            name = device_name.get("name")
            if isinstance(name, str) and name:
                next_snapshot.name = name

        power = update.get("power")
        if isinstance(power, dict):
            known = power.get("known")
            if isinstance(known, dict):
                battery_status = known.get("battery_status")
                mapped_state = None
                if battery_status == "CHARGING":
                    mapped_state = types.PowerState.CHARGING
                elif battery_status == "CHARGED":
                    mapped_state = types.PowerState.CHARGED
                elif battery_status == "DISCHARGING":
                    mapped_state = types.PowerState.DISCHARGING
                next_snapshot.power = types.StatusPower(
                    state=mapped_state,
                    battery_charge=known.get("battery_charge_percent"),
                    battery_voltage=known.get("battery_voltage_mv"),
                    battery_current=known.get("battery_current_ma"),
                    usb_voltage=known.get("usb_voltage_mv"),
                )

        wifi = update.get("wifi")
        if isinstance(wifi, dict):
            connected = wifi.get("connected")
            disconnected = wifi.get("disconnected")
            if isinstance(connected, dict):
                state_value = types.WifiState.CONNECTED
                next_snapshot.wifi = types.StatusResponse(
                    state=state_value,
                    ssid=connected.get("ssid"),
                    bssid=connected.get("bssid"),
                    channel=connected.get("channel"),
                    rssi=connected.get("rssi"),
                )
            elif disconnected is not None:
                next_snapshot.wifi = types.StatusResponse(
                    state=types.WifiState.DISCONNECTED
                )

        brightness = update.get("brightness")
        if isinstance(brightness, dict):
            actual = brightness.get("actual_brightness")
            if actual is not None:
                front = str(actual)
                back = (
                    None
                    if next_snapshot.brightness is None
                    else next_snapshot.brightness.back
                )
                next_snapshot.brightness = types.DisplayBrightnessInfo(
                    front=front,
                    back=back,
                )

        audio_volume = update.get("audio_volume")
        if isinstance(audio_volume, dict):
            volume = audio_volume.get("volume")
            if volume is not None:
                next_snapshot.volume = types.AudioVolumeInfo(volume=float(volume))

        update_check = update.get("update_check")
        if isinstance(update_check, dict):
            available = update_check.get("available")
            next_snapshot.field_errors.pop("update_available", None)
            if isinstance(available, dict):
                next_snapshot.field_errors["update_available"] = (
                    f"available:{available.get('version', '')}"
                )

        ble = update.get("ble")
        if isinstance(ble, dict):
            status = ble.get("status")
            if isinstance(status, str):
                next_snapshot.ble = types.BleStatus(state=status.lower())

        timezone = update.get("timezone")
        if isinstance(timezone, dict):
            # Keep latest timezone payload in raw_time for diagnostics.
            next_snapshot.raw_time = timezone

    return next_snapshot
