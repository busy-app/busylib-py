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
    ServiceInfo,
    ServiceStateChange,
    Zeroconf,
    InterfaceChoice,
)
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

BUSYBAR_SERVICE = "_http._tcp.local."
# Firmware advertises the bar's unique instance name as "busybar-<mac>" under
# the shared _http service (not a dedicated _busybar service), so it must be
# stripped to recover the device id.
BUSYBAR_INSTANCE_NAME_PREFIX = "busybar-"
BUSYBAR_USB_SUBNET = "10.0.4."
BUSYBAR_DEFAULT_NAME = b"BUSY Bar"
TIMEOUT = 1.5
# How long to wait for one bar to answer with its full record, in ms.
RESOLVE_TIMEOUT_MS = 1500.0


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


class _DeviceCollector:
    """
    Turns resolved mDNS records into `BusyBarDevice` values.

    Shared by the sync and async discoverers, which differ only in how they
    talk to zeroconf.
    """

    def __init__(self) -> None:
        self._devices_by_id: dict[str, BusyBarDevice] = {}

    def collected(self) -> list[BusyBarDevice]:
        return list(self._devices_by_id.values())

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

    @staticmethod
    def _is_interesting(state_change: ServiceStateChange) -> bool:
        return state_change in (
            ServiceStateChange.Added,
            ServiceStateChange.Updated,
        )

    def _record(self, info: ServiceInfo) -> None:
        """
        Fold one resolved service record into the collected devices.

        `_http._tcp` is a generic service type, so other, unrelated HTTP
        servers on the network may answer too; only instances following the
        bar's naming convention are treated as bars.
        """
        instance_name = info.name.split(".")[0]
        if not instance_name.startswith(BUSYBAR_INSTANCE_NAME_PREFIX):
            return
        device_id = instance_name.removeprefix(BUSYBAR_INSTANCE_NAME_PREFIX)
        addresses = (
            BusyBarDeviceDiscoverer._ip_address_to_our(addr.compressed)
            for addr in info.ip_addresses_by_version(IPVersion.V4Only)
        )

        raw_name = info.properties.get(b"name") or BUSYBAR_DEFAULT_NAME
        device_name = raw_name.decode("utf-8", errors="replace")
        default_device = BusyBarDevice(
            name=device_name, device_id=device_id, addresses=set()
        )
        device = self._devices_by_id.get(device_id, default_device)
        device.addresses = device.addresses.union(addresses)
        self._devices_by_id[device_id] = device


class BusyBarDeviceDiscoverer(_DeviceCollector):
    """
    Blocking mDNS discovery.

    Owns the `Zeroconf` instance it creates and closes it when done. One
    supplied by the caller is left exactly as it was found: not reconfigured,
    and not closed, because they may still be using it.
    """

    def __init__(self, zeroconf: Zeroconf | None) -> None:
        super().__init__()
        self._user_provided_zeroconf = zeroconf is not None
        # A bar plugged in over USB answers on a 10.0.4.x link, so every
        # interface has to be listened on. That is already Zeroconf's own
        # default, which is why a caller's instance needs no adjustment - and
        # if they deliberately narrowed theirs, overriding it would be wrong.
        self._zeroconf = zeroconf or Zeroconf(InterfaceChoice.All)

    def sync_teardown(self) -> None:
        """
        Close the `Zeroconf` instance, if this discoverer created it.
        """
        if not self._user_provided_zeroconf:
            self._zeroconf.close()

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if not self._is_interesting(state_change):
            return
        info = zeroconf.get_service_info(service_type, name)
        if info:
            self._record(info)

    def sync_collect(self, timeout: float) -> list[BusyBarDevice]:
        with ServiceBrowser(
            self._zeroconf, BUSYBAR_SERVICE, handlers=[self._on_service_state_change]
        ):
            time.sleep(timeout)
        return self.collected()


class AsyncBusyBarDeviceDiscoverer(_DeviceCollector):
    """
    Non-blocking mDNS discovery, on zeroconf's own async API.

    Nothing here reaches for a worker thread: `AsyncZeroconf` closes with
    `async_close`, the browser cancels with `async_cancel`, and records are
    resolved with `AsyncServiceInfo.async_request` instead of the blocking
    `get_service_info`.
    """

    def __init__(self, zeroconf: AsyncZeroconf | None) -> None:
        super().__init__()
        self._user_provided_zeroconf = zeroconf is not None
        self._aiozc = zeroconf or AsyncZeroconf(InterfaceChoice.All)
        self._pending: set[asyncio.Task[None]] = set()

    async def async_teardown(self) -> None:
        """
        Close the `AsyncZeroconf` instance, if this discoverer created it.
        """
        if not self._user_provided_zeroconf:
            await self._aiozc.async_close()

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if not self._is_interesting(state_change):
            return
        # Handlers run on the event loop thread, so resolving has to be
        # scheduled rather than awaited here. The task is kept referenced
        # until it finishes, otherwise it can be garbage collected mid-flight.
        task = asyncio.ensure_future(self._resolve(service_type, name))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _resolve(self, service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        if await info.async_request(self._aiozc.zeroconf, RESOLVE_TIMEOUT_MS):
            self._record(info)

    async def async_collect(self, timeout: float) -> list[BusyBarDevice]:
        browser = AsyncServiceBrowser(
            self._aiozc.zeroconf,
            BUSYBAR_SERVICE,
            handlers=[self._on_service_state_change],
        )
        try:
            await asyncio.sleep(timeout)
        finally:
            await browser.async_cancel()
        # A record announced just before the deadline may still be resolving.
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
        return self.collected()


class BusyBarDevices:
    @staticmethod
    async def async_discover(
        timeout: float = TIMEOUT, zeroconf: AsyncZeroconf | None = None
    ) -> list[BusyBarDevice]:
        """
        Discover bars without blocking the event loop.

        Takes an `AsyncZeroconf`, not a `Zeroconf`, mirroring zeroconf's own
        split between the two APIs. Wrap an existing instance with
        `AsyncZeroconf(zc=my_zeroconf)` if you already have one.
        """
        discoverer = AsyncBusyBarDeviceDiscoverer(zeroconf)
        try:
            return await discoverer.async_collect(timeout)
        finally:
            await discoverer.async_teardown()

    @staticmethod
    def discover(
        timeout: float = TIMEOUT, zeroconf: Zeroconf | None = None
    ) -> list[BusyBarDevice]:
        discoverer = BusyBarDeviceDiscoverer(zeroconf)
        try:
            return discoverer.sync_collect(timeout)
        finally:
            discoverer.sync_teardown()
