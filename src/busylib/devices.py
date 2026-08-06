from __future__ import annotations
from typing import Literal
from dataclasses import dataclass
from enum import Enum
import asyncio

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


class BusyBarDevices:
    @staticmethod
    def _address_affinity(address: str) -> BusyBarAddressAffinity:
        if address.startswith(BUSYBAR_USB_SUBNET):
            return BusyBarAddressAffinity.OVER_USB
        else:
            return BusyBarAddressAffinity.OVER_WIFI

    @staticmethod
    def _ip_address_to_our(address: str) -> BusyBarAddress:
        return BusyBarAddress(
            ip_address=address, affinity=BusyBarDevices._address_affinity(address)
        )

    @staticmethod
    async def discover(
        timeout: float = TIMEOUT, zeroconf: Zeroconf | None = None
    ) -> list[BusyBarDevice]:
        internal_short_lived_zeroconf = not bool(zeroconf)
        if internal_short_lived_zeroconf:
            zeroconf = Zeroconf(InterfaceChoice.All)
        else:
            await zeroconf.async_update_interfaces(InterfaceChoice.All)

        devices_by_id: dict[str, BusyBarDevice] = {}

        def _on_service_state_change(
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
                BusyBarDevices._ip_address_to_our(addr.compressed) for addr in addresses
            )

            raw_name = info.properties.get(b"name") or BUSYBAR_DEFAULT_NAME
            device_name = raw_name.decode("utf-8", errors="replace")
            default_device = BusyBarDevice(
                name=device_name, device_id=device_id, addresses=set()
            )
            device = devices_by_id.get(device_id, default_device)
            device.addresses = device.addresses.union(addresses)
            devices_by_id[device_id] = device

        with ServiceBrowser(
            zeroconf, BUSYBAR_SERVICE, handlers=[_on_service_state_change]
        ):
            await asyncio.sleep(timeout)

        if internal_short_lived_zeroconf:
            zeroconf.close()

        return list(devices_by_id.values())
