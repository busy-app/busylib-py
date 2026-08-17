from __future__ import annotations

import threading

import pytest

from busylib import AsyncBusyBar, BusyBar
from busylib.devices import (
    BusyBarAddress,
    BusyBarAddressAffinity,
    BusyBarDevice,
    BusyBarDeviceDiscoverer,
    BusyBarDevices,
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


class RecordingZeroconf:
    """
    Stands in for a caller-supplied `Zeroconf`, recording what is done to it.
    """

    def __init__(self) -> None:
        self.closed_on_thread: int | None = None
        self.reconfigured = False

    def close(self) -> None:
        self.closed_on_thread = threading.get_ident()

    def update_interfaces(self, *_args: object, **_kwargs: object) -> None:
        self.reconfigured = True

    async def async_update_interfaces(self, *_args: object, **_kwargs: object) -> None:
        self.reconfigured = True


def test_discover_leaves_a_caller_supplied_zeroconf_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Neither closed nor reconfigured, because the caller still owns it.

    Discovery needs every interface listened on, but that is already
    Zeroconf's own default. Forcing `InterfaceChoice.All` onto a caller's
    instance only overrode a narrowing they had chosen on purpose, and left it
    that way after discovery had finished.

    Driven through `discover()` rather than the discoverer, because that is
    where the reconfiguration used to happen.
    """
    zeroconf = RecordingZeroconf()
    monkeypatch.setattr(BusyBarDeviceDiscoverer, "sync_collect", lambda *_: [])

    assert BusyBarDevices.discover(zeroconf=zeroconf) == []  # type: ignore[arg-type]

    assert zeroconf.closed_on_thread is None
    assert not zeroconf.reconfigured


@pytest.mark.asyncio
async def test_async_discover_leaves_a_caller_supplied_zeroconf_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The async path leaves it alone too.
    """
    zeroconf = RecordingZeroconf()

    async def no_devices(*_args: object) -> list[BusyBarDevice]:
        return []

    monkeypatch.setattr(BusyBarDeviceDiscoverer, "async_collect", no_devices)

    assert await BusyBarDevices.async_discover(zeroconf=zeroconf) == []  # type: ignore[arg-type]

    assert zeroconf.closed_on_thread is None
    assert not zeroconf.reconfigured


def test_an_owned_zeroconf_is_closed() -> None:
    """
    The instance the discoverer created is its responsibility to close.
    """
    discoverer = BusyBarDeviceDiscoverer(None)
    owned = RecordingZeroconf()
    discoverer._zeroconf = owned  # type: ignore[assignment]

    discoverer.sync_teardown()

    assert owned.closed_on_thread == threading.get_ident()


@pytest.mark.asyncio
async def test_async_teardown_closes_off_the_event_loop() -> None:
    """
    `Zeroconf.close()` joins listener threads and has no async form in
    zeroconf 0.150, so awaiting it directly would stall the loop. It has to
    run on a worker thread.
    """
    discoverer = BusyBarDeviceDiscoverer(None)
    owned = RecordingZeroconf()
    discoverer._zeroconf = owned  # type: ignore[assignment]

    await discoverer.async_teardown()

    assert owned.closed_on_thread is not None
    assert owned.closed_on_thread != threading.get_ident()


def test_discover_closes_its_zeroconf_when_collection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A timeout mid-scan must not leak the sockets.
    """
    owned = RecordingZeroconf()

    def fake_init(self: BusyBarDeviceDiscoverer, zeroconf: object) -> None:
        self._user_provided_zeroconf = False
        self._zeroconf = owned  # type: ignore[assignment]
        self._devices_by_id = {}

    def boom(_self: BusyBarDeviceDiscoverer, _timeout: float) -> list[BusyBarDevice]:
        raise TimeoutError("scan interrupted")

    monkeypatch.setattr(BusyBarDeviceDiscoverer, "__init__", fake_init)
    monkeypatch.setattr(BusyBarDeviceDiscoverer, "sync_collect", boom)

    with pytest.raises(TimeoutError):
        BusyBarDevices.discover()

    assert owned.closed_on_thread is not None


@pytest.mark.asyncio
async def test_async_discover_closes_its_zeroconf_when_collection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Same for the async path, including cancellation.
    """
    owned = RecordingZeroconf()

    def fake_init(self: BusyBarDeviceDiscoverer, zeroconf: object) -> None:
        self._user_provided_zeroconf = False
        self._zeroconf = owned  # type: ignore[assignment]
        self._devices_by_id = {}

    async def boom(_self: BusyBarDeviceDiscoverer, _timeout: float) -> None:
        raise TimeoutError("scan interrupted")

    monkeypatch.setattr(BusyBarDeviceDiscoverer, "__init__", fake_init)
    monkeypatch.setattr(BusyBarDeviceDiscoverer, "async_collect", boom)

    with pytest.raises(TimeoutError):
        await BusyBarDevices.async_discover()

    assert owned.closed_on_thread is not None
