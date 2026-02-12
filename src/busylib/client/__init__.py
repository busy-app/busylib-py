from __future__ import annotations

import logging

from .access import AccessMixin, AsyncAccessMixin
from .account import AccountMixin, AsyncAccountMixin
from .busy import AsyncBusyMixin, BusyMixin
from .assets import AssetsMixin, AsyncAssetsMixin
from .audio import AsyncAudioMixin, AudioMixin
from .base import AsyncClientBase, SyncClientBase
from .ble import AsyncBleMixin, BleMixin
from .display import AsyncDisplayMixin, DisplayMixin
from .firmware import AsyncFirmwareMixin, FirmwareMixin
from .input import AsyncInputMixin, InputMixin
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
    BleMixin,
    SyncClientBase,
):
    """
    HTTPX-based client for the Busy Bar API.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
    AsyncBleMixin,
    AsyncClientBase,
):
    """
    Async HTTPX-based client for the Busy Bar API.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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


__all__ = ["BusyBar", "AsyncBusyBar"]
