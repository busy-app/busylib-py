from __future__ import annotations

from typing import cast

import pytest

from busylib.client import AsyncBusyBar
from busylib import types
from busylib.features import (
    DeviceSnapshot,
    DeviceStateStore,
    apply_state_stream_update,
    collect_device_snapshot,
)


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


def test_apply_state_stream_update_updates_known_fields() -> None:
    """
    Apply protobuf state updates to an existing snapshot.

    This verifies name, power, brightness, volume, and Wi-Fi fields are mapped
    from streamed state payloads.
    """
    start = DeviceSnapshot(
        name="Old",
        brightness=types.DisplayBrightnessInfo(front="10", back="15"),
    )
    payload = {
        "updates": [
            {"device_name": {"name": "BUSY"}},
            {
                "power": {
                    "known": {
                        "battery_status": "CHARGING",
                        "battery_charge_percent": 77,
                        "battery_voltage_mv": 4100,
                        "battery_current_ma": -120,
                        "usb_voltage_mv": 5000,
                    }
                }
            },
            {"brightness": {"actual_brightness": 22}},
            {"audio_volume": {"volume": 35}},
            {
                "wifi": {
                    "connected": {
                        "ssid": "Office",
                        "bssid": "aa:bb:cc:dd:ee:ff",
                        "channel": 6,
                        "rssi": -55,
                    }
                }
            },
        ]
    }

    updated = apply_state_stream_update(start, payload)
    assert updated.name == "BUSY"
    assert updated.power is not None
    assert updated.power.state is types.PowerState.CHARGING
    assert updated.power.battery_charge == 77
    assert updated.brightness is not None
    assert updated.brightness.front == "22"
    assert updated.brightness.back == "15"
    assert updated.volume is not None
    assert updated.volume.volume == 35.0
    assert updated.wifi is not None
    assert updated.wifi.state is types.WifiState.CONNECTED
    assert updated.wifi.ssid == "Office"


def test_apply_state_stream_update_keeps_existing_when_no_updates() -> None:
    """
    Keep snapshot intact when stream payload has no usable updates.
    """
    start = DeviceSnapshot(
        name="Stable",
        volume=types.AudioVolumeInfo(volume=44),
    )
    updated = apply_state_stream_update(start, {"updates": []})
    assert updated.name == "Stable"
    assert updated.volume is not None
    assert updated.volume.volume == 44


def test_apply_state_stream_update_sets_update_available_version() -> None:
    """
    Map update-check availability into dedicated snapshot field.

    This keeps diagnostic field_errors reserved for collection failures.
    """
    start = DeviceSnapshot(name="Stable", field_errors={"volume": "x"})
    payload = {
        "updates": [
            {"update_check": {"available": {"version": "1.2.3"}}},
        ]
    }
    updated = apply_state_stream_update(start, payload)
    assert updated.update_available_version == "1.2.3"
    assert updated.field_errors == {"volume": "x"}


def test_device_state_store_emits_diff_and_state_callbacks() -> None:
    """
    Emit callbacks with changed fields after applying state stream updates.

    The store should notify both channels exactly once per meaningful change.
    """
    store = DeviceStateStore(
        DeviceSnapshot(
            name="Old",
            brightness=types.DisplayBrightnessInfo(front="10", back="15"),
        )
    )

    seen_state: list[DeviceSnapshot] = []
    seen_diff: list[tuple[set[str], DeviceSnapshot]] = []

    store.on_state(lambda snapshot: seen_state.append(snapshot))
    store.on_diff(lambda changed, snapshot: seen_diff.append((changed, snapshot)))

    store.apply_stream_message(
        {
            "updates": [
                {"device_name": {"name": "New"}},
                {"brightness": {"actual_brightness": 22}},
            ]
        }
    )

    assert len(seen_state) == 1
    assert len(seen_diff) == 1
    changed, snapshot = seen_diff[0]
    assert changed == {"name", "brightness"}
    assert snapshot.name == "New"
    assert snapshot.brightness is not None
    assert snapshot.brightness.front == "22"
    assert seen_state[0].name == "New"


def test_device_state_store_unsubscribe_stops_callbacks() -> None:
    """
    Stop receiving notifications after unsubscribing from store callbacks.

    This keeps callback lifecycle explicit and prevents stale listeners.
    """
    store = DeviceStateStore(DeviceSnapshot(name="Old"))
    state_calls = 0
    diff_calls = 0

    def _on_state(_snapshot: DeviceSnapshot) -> None:
        nonlocal state_calls
        state_calls += 1

    def _on_diff(_changed: set[str], _snapshot: DeviceSnapshot) -> None:
        nonlocal diff_calls
        diff_calls += 1

    off_state = store.on_state(_on_state)
    off_diff = store.on_diff(_on_diff)
    off_state()
    off_diff()

    store.apply_stream_message({"updates": [{"device_name": {"name": "New"}}]})

    assert state_calls == 0
    assert diff_calls == 0
