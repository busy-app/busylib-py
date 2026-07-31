from __future__ import annotations

import getpass

from busylib import BusyBar, BusyBarDevices
from busylib.devices import BusyBarDevice
from busylib.types import HttpAccessInfo

DISCOVERY_TIMEOUT_SECONDS = 1.5

# Well-known static address of a USB-connected bar. Falls back to this when
# mDNS discovery finds nothing - factory firmware doesn't advertise
# `_busybar._tcp` yet (that feature isn't merged/released), so a bar
# connected over USB is otherwise unreachable without an explicit --addr.
USB_FALLBACK_ADDRESS = "10.0.4.20"


def _device_address(device: BusyBarDevice) -> str | None:
    return device.get_address("over_wifi") or device.get_address("over_usb")


def _prompt_device_choice(devices: list[BusyBarDevice]) -> BusyBarDevice:
    """
    Print a numbered menu of discovered devices and prompt for a selection.
    """
    print("Found multiple BUSY Bar devices:")
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
        print(f"Found one BUSY Bar device: {device.name}")
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
    Discover BUSY Bar devices on the network and resolve address + token.

    Used when the user did not pass --addr explicitly: finds devices via
    mDNS, lets the user pick one by name if more than one is found, and
    prompts for an access key/PIN when the selected device requires one and
    no --token was given.
    """
    print("No --addr given; discovering BUSY Bar devices on the network...")
    devices = BusyBarDevices.discover(timeout=timeout)

    if devices:
        device = _select_device(devices)
        addr = _device_address(device)
        if addr is None:
            raise SystemExit(f"Device {device.name} has no usable IP address.")
        device_label = device.name
    else:
        print(
            "No devices found via mDNS discovery (bar discovery isn't in "
            "shipped firmware yet). Trying the well-known USB address "
            f"{USB_FALLBACK_ADDRESS}..."
        )
        addr = USB_FALLBACK_ADDRESS
        device_label = f"device at {USB_FALLBACK_ADDRESS}"

    access_info = _probe_access_mode(addr, token)
    if access_info is None:
        if not devices:
            raise SystemExit(
                "No BUSY Bar devices found via mDNS, and the USB fallback "
                f"address {USB_FALLBACK_ADDRESS} isn't reachable either. "
                "Pass --addr explicitly."
            )
        # Access mode couldn't be verified (e.g. the probe request itself
        # failed) - ask anyway rather than silently connecting without a
        # token and failing later with a much less clear error.
        print(
            "Could not verify the device's access mode (GET /api/access "
            "failed); asking for an access key just in case."
        )
        confirmed_no_key_needed = False
    else:
        # `key_valid` reflects whether the device already has a key
        # provisioned at all, not whether *our* (possibly absent) token
        # matches it - so it must not be used to skip the prompt.
        confirmed_no_key_needed = access_info.mode != "key"

    if not confirmed_no_key_needed and not token:
        entered = getpass.getpass(
            f"Enter access key/PIN for {device_label} (leave blank if none): "
        ).strip()
        token = entered or token

    return addr, token
