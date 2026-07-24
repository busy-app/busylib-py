from __future__ import annotations

import pytest

from busylib.devices import BusyBarAddress, BusyBarAddressAffinity, BusyBarDevice
from busylib.types import HttpAccessInfo
from examples.remote import discovery


def _device(name: str, ip: str, temporary_id: str = "id") -> BusyBarDevice:
    return BusyBarDevice(
        name=name,
        temporary_id=temporary_id,
        addresses={
            BusyBarAddress(
                ip_address=ip,
                affinity=BusyBarAddressAffinity.OVER_WIFI,
            )
        },
    )


def test_resolve_connection_no_devices_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Raise a clear, actionable error when discovery finds nothing.
    """
    monkeypatch.setattr(discovery.BusyBarDevices, "discover", lambda timeout=1.5: [])
    with pytest.raises(SystemExit, match="No Busy Bar devices found"):
        discovery.resolve_connection(None)


def test_resolve_connection_single_device_no_key_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Auto-select the only device and skip the PIN prompt when unprotected.
    """
    device = _device("Tug's bar", "192.168.1.20")
    monkeypatch.setattr(
        discovery.BusyBarDevices, "discover", lambda timeout=1.5: [device]
    )
    monkeypatch.setattr(
        discovery,
        "_probe_access_mode",
        lambda addr, token: HttpAccessInfo(mode="enabled", key_valid=None),
    )

    def _fail_input(_prompt: str) -> str:
        raise AssertionError("should not prompt when access mode isn't 'key'")

    monkeypatch.setattr("builtins.input", _fail_input)

    addr, token = discovery.resolve_connection(None)
    assert addr == "192.168.1.20"
    assert token is None


def test_resolve_connection_prompts_for_key_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Prompt for an access key/PIN when the device requires one and none was given.
    """
    device = _device("Tug's bar", "192.168.1.20")
    monkeypatch.setattr(
        discovery.BusyBarDevices, "discover", lambda timeout=1.5: [device]
    )
    monkeypatch.setattr(
        discovery,
        "_probe_access_mode",
        lambda addr, token: HttpAccessInfo(mode="key", key_valid=False),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "1234")

    addr, token = discovery.resolve_connection(None)
    assert addr == "192.168.1.20"
    assert token == "1234"


def test_resolve_connection_skips_prompt_when_token_already_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Don't prompt again when a valid --token was already supplied.
    """
    device = _device("Tug's bar", "192.168.1.20")
    monkeypatch.setattr(
        discovery.BusyBarDevices, "discover", lambda timeout=1.5: [device]
    )
    monkeypatch.setattr(
        discovery,
        "_probe_access_mode",
        lambda addr, token: HttpAccessInfo(mode="key", key_valid=True),
    )

    def _fail_input(_prompt: str) -> str:
        raise AssertionError("should not prompt when the existing token is valid")

    monkeypatch.setattr("builtins.input", _fail_input)

    addr, token = discovery.resolve_connection("already-valid")
    assert addr == "192.168.1.20"
    assert token == "already-valid"


def test_resolve_connection_multiple_devices_prompts_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Show a numbered menu and use the user's selection when multiple bars are found.
    """
    first = _device("Front desk", "192.168.1.10", temporary_id="a")
    second = _device("Kitchen", "192.168.1.11", temporary_id="b")
    monkeypatch.setattr(
        discovery.BusyBarDevices, "discover", lambda timeout=1.5: [first, second]
    )
    monkeypatch.setattr(
        discovery,
        "_probe_access_mode",
        lambda addr, token: HttpAccessInfo(mode="disabled", key_valid=None),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    addr, token = discovery.resolve_connection(None)
    assert addr == "192.168.1.11"
    assert token is None


def test_resolve_connection_device_without_address_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Raise a clear error when the selected device has no usable IP.
    """
    device = BusyBarDevice(name="No IP", temporary_id="id", addresses=set())
    monkeypatch.setattr(
        discovery.BusyBarDevices, "discover", lambda timeout=1.5: [device]
    )
    with pytest.raises(SystemExit, match="no usable IP address"):
        discovery.resolve_connection(None)
