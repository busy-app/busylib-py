from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
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
    raw_time: object | None = Field(default=None, exclude=True)

    model_config = {"extra": "ignore"}


async def _safe(call: Coroutine | asyncio.Future | object) -> object:
    try:
        return await call if asyncio.iscoroutine(call) else call
    except Exception as exc:  # noqa: BLE001
        logger.debug("Snapshot field failed: %s", exc)
        return None


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
    tasks = {
        "name": asyncio.create_task(_safe(client.get_device_name())),
        "version": asyncio.create_task(_safe(client.get_version())),
        "status": asyncio.create_task(_safe(client.get_status())),
        "system": asyncio.create_task(_safe(client.get_system_status())),
        "power": asyncio.create_task(_safe(client.get_power_status())),
        "time": asyncio.create_task(_safe(client.get_device_time())),
        "wifi": asyncio.create_task(_safe(client.get_wifi_status())),
        "brightness": asyncio.create_task(_safe(client.get_display_brightness())),
        "volume": asyncio.create_task(_safe(client.get_audio_volume())),
        "ble": asyncio.create_task(_safe(client.ble_status())),
        "storage": asyncio.create_task(_safe(client.get_storage_status())),
    }

    results: dict[str, object | None] = {}
    for key, task in tasks.items():
        results[key] = await task

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
        raw_time=raw_time,
    )
