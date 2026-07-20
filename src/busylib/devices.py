from __future__ import annotations
from typing import Literal
from dataclasses import dataclass
from enum import Enum
from time import sleep

from zeroconf import (
    IPVersion,
    ServiceBrowser,
    ServiceStateChange,
    Zeroconf,
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
    temporary_id: str
    addresses: set[BusyBarAddress]

    def get_address(self, affinity: Literal["over_usb"]|Literal["over_wifi"]) -> str|None:
        for addr in self.addresses:
            if addr.affinity.value == affinity:
                return addr.ip_address
        return None

class BusyBarDevices:
    @staticmethod
    def _address_affinity(address: str) -> BusyBarAddressAffinity:
        if address.startswith(BUSYBAR_USB_SUBNET):
            return BusyBarAddressAffinity.OVER_USB
        else:
            return BusyBarAddressAffinity.OVER_WIFI

    @staticmethod
    def _ip_address_to_our(address: str) -> BusyBarAddress:
        return BusyBarAddress(ip_address=address, affinity=BusyBarDevices._address_affinity(address))

    @staticmethod
    def discover(timeout: float = TIMEOUT, zeroconf: Zeroconf | None = None) -> list[BusyBarDevice]:
        if not zeroconf:
            zeroconf = Zeroconf()

        devices_by_id: dict[str, BusyBarDevice] = {}

        def _on_service_state_change(
            zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
        ) -> None:
            if state_change not in [ServiceStateChange.Added, ServiceStateChange.Updated]:
                return
            
            info = zeroconf.get_service_info(service_type, name)
            if not info:
                return
            
            temporary_id = info.name.split(".")[0]
            addresses = info.ip_addresses_by_version(IPVersion.V4Only)
            addresses = (BusyBarDevices._ip_address_to_our(addr.compressed) for addr in addresses)

            raw_name = info.properties.get(b"name") or BUSYBAR_DEFAULT_NAME
            device_name = raw_name.decode("utf-8", errors="replace")
            default_device = BusyBarDevice(name=device_name, temporary_id=temporary_id, addresses=set())
            device = devices_by_id.get(temporary_id, default_device)
            device.addresses = device.addresses.union(addresses)
            devices_by_id[temporary_id] = device

        ServiceBrowser(zeroconf, BUSYBAR_SERVICE, handlers=[_on_service_state_change])
        sleep(timeout)
        zeroconf.close()

        return list(devices_by_id.values())
