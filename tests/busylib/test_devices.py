from __future__ import annotations

import pytest

from busylib import AsyncBusyBar, BusyBar
from busylib.devices import (
    BusyBarAddress,
    BusyBarAddressAffinity,
    BusyBarDevice,
)

USB_IP = "10.0.4.20"
WIFI_IP = "192.168.1.20"


def _device(*, usb: bool = True, wifi: bool = True) -> BusyBarDevice:
    addresses = set()
    if usb:
        addresses.add(
            BusyBarAddress(ip_address=USB_IP, affinity=BusyBarAddressAffinity.OVER_USB)
        )
    if wifi:
        addresses.add(
            BusyBarAddress(
                ip_address=WIFI_IP, affinity=BusyBarAddressAffinity.OVER_WIFI
            )
        )
    return BusyBarDevice(name="bar", device_id="aabbcc", addresses=addresses)


@pytest.mark.parametrize(
    "affinity,expected",
    [("over_usb", USB_IP), ("over_wifi", WIFI_IP)],
)
def test_get_address_selects_by_affinity(affinity: str, expected: str) -> None:
    """
    Each transport resolves to its own address.
    """
    assert _device().get_address(affinity) == expected  # type: ignore[arg-type]


def test_get_address_prefers_usb_when_unspecified() -> None:
    """
    With no affinity given, USB wins over Wi-Fi.

    A USB link is present only when the bar is plugged into this machine,
    so it is the more specific answer of the two.
    """
    assert _device().get_address() == USB_IP
    assert _device(usb=False).get_address() == WIFI_IP


def test_get_address_returns_none_when_the_transport_is_absent() -> None:
    """
    Asking for a transport the device doesn't have yields None.
    """
    assert _device(usb=False).get_address("over_usb") is None
    assert BusyBarDevice(name="x", device_id="y", addresses=set()).get_address() is None


def test_client_factories_build_clients_for_the_right_address() -> None:
    """
    The factories hand back a client pointed at the chosen transport.
    """
    device = _device()

    assert isinstance(device.to_sync_client(), BusyBar)
    assert isinstance(device.to_async_client(), AsyncBusyBar)

    over_usb = device.to_sync_client("over_usb")
    over_wifi = device.to_sync_client("over_wifi")
    assert over_usb is not None and over_wifi is not None
    assert USB_IP in over_usb.base_url
    assert WIFI_IP in over_wifi.base_url


def test_client_factories_forward_keyword_arguments() -> None:
    """
    Extra arguments reach the client, which is how a token is passed.
    """
    client = _device().to_sync_client("over_wifi", token="1234")

    assert client is not None
    assert client.client.headers.get("X-API-Token") == "1234"


def test_client_factories_return_none_without_an_address() -> None:
    """
    No usable address means no client, rather than one pointed at nothing.
    """
    device = _device(usb=False)

    assert device.to_sync_client("over_usb") is None
    assert device.to_async_client("over_usb") is None
