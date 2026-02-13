from __future__ import annotations

from typing import cast

import pytest

from busylib.client import AsyncBusyBar
from busylib import types
from busylib.features import collect_device_snapshot


class _OkClient:
    """
    Async client stub with successful responses for all dashboard fields.

    The stub returns minimal payloads compatible with target response models.
    """

    async def get_device_name(self) -> types.DeviceNameResponse:
        """
        Return a valid device name payload.
        """
        return types.DeviceNameResponse(name="Busy")

    async def get_version(self) -> types.VersionInfo:
        """
        Return a valid version payload.
        """
        return types.VersionInfo(api_semver="1.0.0")

    async def get_status(self) -> types.Status:
        """
        Return a valid status payload.
        """
        return types.Status()

    async def get_system_status(self) -> types.StatusSystem:
        """
        Return a valid system status payload.
        """
        return types.StatusSystem()

    async def get_power_status(self) -> types.StatusPower:
        """
        Return a valid power status payload.
        """
        return types.StatusPower()

    async def get_device_time(self) -> types.DeviceTimeResponse:
        """
        Return a valid ISO timestamp payload.
        """
        return types.DeviceTimeResponse(timestamp="2024-01-01T10:00:00")

    async def get_wifi_status(self) -> types.StatusResponse:
        """
        Return a valid Wi-Fi status payload.
        """
        return types.StatusResponse(state=types.WifiState.CONNECTED)

    async def get_display_brightness(self) -> types.DisplayBrightnessInfo:
        """
        Return a valid display brightness payload.
        """
        return types.DisplayBrightnessInfo(front="10", back="10")

    async def get_audio_volume(self) -> types.AudioVolumeInfo:
        """
        Return a valid audio volume payload.
        """
        return types.AudioVolumeInfo(volume=50.0)

    async def ble_status(self) -> types.BleStatus:
        """
        Return a valid BLE status payload.
        """
        return types.BleStatus(state="on")

    async def get_storage_status(self) -> types.StorageStatus:
        """
        Return a valid storage payload.
        """
        return types.StorageStatus(total_bytes=100, used_bytes=20)


class _VolumeFailClient(_OkClient):
    """
    Async client stub with a single failing field for diagnostics coverage.

    All fields succeed except `get_audio_volume`.
    """

    async def get_audio_volume(self) -> types.AudioVolumeInfo:
        """
        Raise a deterministic error for field-level failure checks.
        """
        raise RuntimeError("audio unavailable")


@pytest.mark.asyncio
async def test_collect_device_snapshot_success_has_no_field_errors() -> None:
    """
    Keep successful collection fully populated without field errors.

    This validates the normal path and ensures diagnostics stay empty.
    """
    snapshot = await collect_device_snapshot(cast(AsyncBusyBar, _OkClient()))

    assert snapshot.name == "Busy"
    assert snapshot.time is not None
    assert snapshot.volume is not None
    assert snapshot.field_errors == {}


@pytest.mark.asyncio
async def test_collect_device_snapshot_keeps_partial_results_and_errors() -> None:
    """
    Preserve partial snapshot data while exposing per-field failure reason.

    This verifies that one failing field does not abort full collection and
    that a structured diagnostic entry is included in the snapshot.
    """
    snapshot = await collect_device_snapshot(cast(AsyncBusyBar, _VolumeFailClient()))

    assert snapshot.name == "Busy"
    assert snapshot.time is not None
    assert snapshot.volume is None
    assert "volume" in snapshot.field_errors
    assert snapshot.field_errors["volume"].startswith("RuntimeError:")
