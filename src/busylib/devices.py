from __future__ import annotations
from typing import Literal
from dataclasses import dataclass
from enum import Enum
import asyncio
import time

from .client import AsyncBusyBar, BusyBar

from zeroconf import (
    IPVersion,
    ServiceBrowser,
    ServiceStateChange,
    Zeroconf,
    InterfaceChoice,
)

BUSYBAR_SERVICE = "_busybar._tcp.local."
BUSYBAR_USB_SUBNET = "10.0.4."
BUSYBAR_DEFAULT_NAME = b"BUSY Bar"
TIMEOUT = 1.5


class BusyBarAddressAffinity(Enum):
    OVER_USB = "over_usb"
    OVER_WIFI = "over_wifi"


@dataclass(unsafe_hash=True)
class BusyBarAddress:
    ip_address: str
    affinity: BusyBarAddressAffinity


@dataclass
class BusyBarDevice:
    name: str
    device_id: str
    addresses: set[BusyBarAddress]

    def get_address(
        self, affinity: Literal["over_usb"] | Literal["over_wifi"] | None = None
    ) -> str | None:
        if affinity is None:
            return self.get_address("over_usb") or self.get_address("over_wifi")
        for addr in self.addresses:
            if addr.affinity.value == affinity:
                return addr.ip_address

        return None

    def to_sync_client(
        self,
        affinity: Literal["over_usb"] | Literal["over_wifi"] | None = None,
        **kwargs,
    ) -> BusyBar | None:
        addr = self.get_address(affinity)
        if not addr:
            return None
        return BusyBar(addr, **kwargs)

    def to_async_client(
        self,
        affinity: Literal["over_usb"] | Literal["over_wifi"] | None = None,
        **kwargs,
    ) -> AsyncBusyBar | None:
        addr = self.get_address(affinity)
        if not addr:
            return None
        return AsyncBusyBar(addr, **kwargs)


class BusyBarDeviceDiscoverer:
    def __init__(self, zeroconf):
        self._user_provided_zeroconf = bool(zeroconf)
        self._zeroconf = zeroconf or Zeroconf(InterfaceChoice.All)
        self._devices_by_id = {}

    def sync_setup(self):
        if self._user_provided_zeroconf:
            self._zeroconf.update_interfaces(InterfaceChoice.All)

    async def async_setup(self):
        if self._user_provided_zeroconf:
            await self._zeroconf.async_update_interfaces(InterfaceChoice.All)

    def sync_teardown(self):
        if not self._user_provided_zeroconf:
            self._zeroconf.close()

    @staticmethod
    def _address_affinity(address: str) -> BusyBarAddressAffinity:
        if address.startswith(BUSYBAR_USB_SUBNET):
            return BusyBarAddressAffinity.OVER_USB
        else:
            return BusyBarAddressAffinity.OVER_WIFI

    @staticmethod
    def _ip_address_to_our(address: str) -> BusyBarAddress:
        return BusyBarAddress(
            ip_address=address,
            affinity=BusyBarDeviceDiscoverer._address_affinity(address),
        )

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change not in [
            ServiceStateChange.Added,
            ServiceStateChange.Updated,
        ]:
            return

        info = zeroconf.get_service_info(service_type, name)
        if not info:
            return

        device_id = info.name.split(".")[0]
        addresses = info.ip_addresses_by_version(IPVersion.V4Only)
        addresses = (
            BusyBarDeviceDiscoverer._ip_address_to_our(addr.compressed)
            for addr in addresses
        )

        raw_name = info.properties.get(b"name") or BUSYBAR_DEFAULT_NAME
        device_name = raw_name.decode("utf-8", errors="replace")
        default_device = BusyBarDevice(
            name=device_name, device_id=device_id, addresses=set()
        )
        device = self._devices_by_id.get(device_id, default_device)
        device.addresses = device.addresses.union(addresses)
        self._devices_by_id[device_id] = device

    def sync_collect(self, timeout: float) -> list[BusyBarDevice]:
        with ServiceBrowser(
            self._zeroconf, BUSYBAR_SERVICE, handlers=[self._on_service_state_change]
        ):
            time.sleep(timeout)
        return list(self._devices_by_id.values())

    async def async_collect(self, timeout: float) -> list[BusyBarDevice]:
        with ServiceBrowser(
            self._zeroconf, BUSYBAR_SERVICE, handlers=[self._on_service_state_change]
        ):
            await asyncio.sleep(timeout)
        return list(self._devices_by_id.values())


class BusyBarDevices:
    @staticmethod
    async def async_discover(
        timeout: float = TIMEOUT, zeroconf: Zeroconf | None = None
    ) -> list[BusyBarDevice]:
        discoverer = BusyBarDeviceDiscoverer(zeroconf)
        await discoverer.async_setup()
        devices = await discoverer.async_collect(timeout)
        discoverer.sync_teardown()
        return devices

    @staticmethod
    def discover(
        timeout: float = TIMEOUT, zeroconf: Zeroconf | None = None
    ) -> list[BusyBarDevice]:
        discoverer = BusyBarDeviceDiscoverer(zeroconf)
        discoverer.sync_setup()
        devices = discoverer.sync_collect(timeout)
        discoverer.sync_teardown()
        return devices
