from __future__ import annotations

import logging

import httpx

from .. import versioning
from .base import DEFAULT_BACKOFF

from .access import AccessMixin, AsyncAccessMixin
from .account import AccountMixin, AsyncAccountMixin
from .busy import AsyncBusyMixin, BusyMixin
from .assets import AssetsMixin, AsyncAssetsMixin
from .audio import AsyncAudioMixin, AudioMixin
from .base import AsyncClientBase, PreparedRequest, SyncClientBase
from .ble import AsyncBleMixin, BleMixin
from .display import AsyncDisplayMixin, DisplayMixin
from .firmware import AsyncFirmwareMixin, FirmwareMixin
from .input import AsyncInputMixin, InputMixin
from .smart_home import AsyncSmartHomeMixin, SmartHomeMixin
from .state_stream import AsyncStateStreamMixin, StateStreamMixin
from .storage import AsyncStorageMixin, StorageMixin
from .time import AsyncTimeMixin, TimeMixin
from .updater import AsyncUpdaterMixin, UpdaterMixin
from .usb import AsyncUsbController, UsbController
from .wifi import AsyncWifiMixin, WifiMixin

logger = logging.getLogger(__name__)


class BusyBar(
    AccessMixin,
    AccountMixin,
    BusyMixin,
    TimeMixin,
    UpdaterMixin,
    FirmwareMixin,
    StorageMixin,
    AssetsMixin,
    DisplayMixin,
    AudioMixin,
    WifiMixin,
    InputMixin,
    SmartHomeMixin,
    StateStreamMixin,
    BleMixin,
    SyncClientBase,
):
    """
    HTTPX-based client for the BUSY Bar API.
    """

    def __init__(
        self,
        addr: str | None = None,
        *,
        token: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int = 2,
        backoff: float = DEFAULT_BACKOFF,
        transport: httpx.BaseTransport | None = None,
        api_version: str | None = None,
        compatibility_mode: versioning.CompatibilityMode = "warn",
        is_cloud: bool | None = None,
    ) -> None:
        """
        Build a client for one bar.

        `addr` is a device address; leaving it out with a `token` reaches the
        bar through the cloud. `is_cloud` states that outright, which is what
        lets a cloud host be named - `addr="https://api.dev.busy.app",
        is_cloud=True` - instead of being inferred from an omitted argument.
        """
        super().__init__(
            addr,
            token=token,
            timeout=timeout,
            max_retries=max_retries,
            backoff=backoff,
            transport=transport,
            api_version=api_version,
            compatibility_mode=compatibility_mode,
            is_cloud=is_cloud,
        )
        self._usb: UsbController | None = None

    @property
    def usb(self) -> UsbController:
        """
        Lazy-loaded USB controller.
        """
        if self._usb is None:
            self._usb = UsbController()
        return self._usb

    @property
    def is_usb_connected(self) -> bool:
        """
        Returns True if a USB device was found and connected.
        """
        return self.usb.is_connected

    def usb_reboot(self, *, raise_on_error: bool = False) -> bool:
        """
        Attempt to reboot the device via USB.

        Returns True on success and False on failure by default.
        If raise_on_error is True, re-raises BusyBarUsbError.
        """
        return self.usb.reboot(raise_on_error=raise_on_error)

    def usb_reset(self, *, raise_on_error: bool = False) -> bool:
        """
        Alias for usb_reboot().

        Provided for callers that prefer "reset" naming.
        """
        return self.usb_reboot(raise_on_error=raise_on_error)


class AsyncBusyBar(
    AsyncAccessMixin,
    AsyncAccountMixin,
    AsyncBusyMixin,
    AsyncTimeMixin,
    AsyncUpdaterMixin,
    AsyncFirmwareMixin,
    AsyncStorageMixin,
    AsyncAssetsMixin,
    AsyncDisplayMixin,
    AsyncAudioMixin,
    AsyncWifiMixin,
    AsyncInputMixin,
    AsyncSmartHomeMixin,
    AsyncStateStreamMixin,
    AsyncBleMixin,
    AsyncClientBase,
):
    """
    Async HTTPX-based client for the BUSY Bar API.
    """

    def __init__(
        self,
        addr: str | None = None,
        *,
        token: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int = 2,
        backoff: float = DEFAULT_BACKOFF,
        transport: httpx.AsyncBaseTransport | None = None,
        api_version: str | None = None,
        compatibility_mode: versioning.CompatibilityMode = "warn",
        is_cloud: bool | None = None,
    ) -> None:
        """
        Build a client for one bar.

        `addr` is a device address; leaving it out with a `token` reaches the
        bar through the cloud. `is_cloud` states that outright, which is what
        lets a cloud host be named - `addr="https://api.dev.busy.app",
        is_cloud=True` - instead of being inferred from an omitted argument.
        """
        super().__init__(
            addr,
            token=token,
            timeout=timeout,
            max_retries=max_retries,
            backoff=backoff,
            transport=transport,
            api_version=api_version,
            compatibility_mode=compatibility_mode,
            is_cloud=is_cloud,
        )
        self._usb: AsyncUsbController | None = None

    @property
    def usb(self) -> AsyncUsbController:
        """
        Lazy-loaded USB controller.
        """
        if self._usb is None:
            self._usb = AsyncUsbController()
        return self._usb

    @property
    def is_usb_connected(self) -> bool:
        """
        Returns True if a USB device was found and connected.
        """
        return self.usb.is_connected

    async def usb_reboot(self, *, raise_on_error: bool = False) -> bool:
        """
        Attempt to reboot the device via USB.
        """
        return await self.usb.reboot(raise_on_error=raise_on_error)

    async def usb_reset(self, *, raise_on_error: bool = False) -> bool:
        """
        Alias for usb_reboot().

        Provided for callers that prefer "reset" naming.
        """
        return await self.usb_reboot(raise_on_error=raise_on_error)


__all__ = ["BusyBar", "AsyncBusyBar", "PreparedRequest"]
