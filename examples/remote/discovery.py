from __future__ import annotations

from busylib import BusyBar, BusyBarDevices
from busylib.devices import BusyBarDevice
from busylib.types import HttpAccessInfo

DISCOVERY_TIMEOUT_SECONDS = 1.5


def _device_address(device: BusyBarDevice) -> str | None:
    return device.get_address("over_wifi") or device.get_address("over_usb")


def _prompt_device_choice(devices: list[BusyBarDevice]) -> BusyBarDevice:
    """
    Print a numbered menu of discovered devices and prompt for a selection.
    """
    print("Found multiple Busy Bar devices:")
    for index, device in enumerate(devices, start=1):
        addr = _device_address(device) or "no usable address"
        print(f"  {index}. {device.name} ({addr})")

    while True:
        raw = input(f"Select a device [1-{len(devices)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(devices):
            return devices[int(raw) - 1]
        print(f"Enter a number between 1 and {len(devices)}.")


def _select_device(devices: list[BusyBarDevice]) -> BusyBarDevice:
    if len(devices) == 1:
        device = devices[0]
        print(f"Found one Busy Bar device: {device.name}")
        return device
    return _prompt_device_choice(devices)


def _probe_access_mode(addr: str, token: str | None) -> HttpAccessInfo | None:
    """
    Best-effort check of the device's HTTP access mode.

    `GET /api/access` is unauthenticated on the firmware, so this can run
    before a token is known. Returns None if the probe itself fails (e.g.
    the device is briefly unreachable) rather than raising.
    """
    try:
        return BusyBar(addr=addr, token=token).access()
    except Exception:
        return None


def resolve_connection(
    token: str | None,
    *,
    timeout: float = DISCOVERY_TIMEOUT_SECONDS,
) -> tuple[str, str | None]:
    """
    Discover Busy Bar devices on the network and resolve address + token.

    Used when the user did not pass --addr explicitly: finds devices via
    mDNS, lets the user pick one by name if more than one is found, and
    prompts for an access key/PIN when the selected device requires one and
    no --token was given.
    """
    print("No --addr given; discovering Busy Bar devices on the network...")
    devices = BusyBarDevices.discover(timeout=timeout)
    if not devices:
        raise SystemExit(
            "No Busy Bar devices found via mDNS discovery. Pass --addr "
            "explicitly if the device isn't discoverable on this network."
        )

    device = _select_device(devices)
    addr = _device_address(device)
    if addr is None:
        raise SystemExit(f"Device {device.name!r} has no usable IP address.")

    access_info = _probe_access_mode(addr, token)
    needs_key = (
        access_info is not None
        and access_info.mode == "key"
        and not access_info.key_valid
    )
    if needs_key and not token:
        entered = input(
            f"Enter access key/PIN for {device.name!r} (leave blank if none): "
        ).strip()
        token = entered or token

    return addr, token
