from __future__ import annotations

import logging

from .assets import AssetsMixin, AsyncAssetsMixin
from .audio import AsyncAudioMixin, AudioMixin
from .base import AsyncClientBase, SyncClientBase
from .ble import AsyncBleMixin, BleMixin
from .display import AsyncDisplayMixin, DisplayMixin
from .firmware import AsyncFirmwareMixin, FirmwareMixin
from .input import AsyncInputMixin, InputMixin
from .storage import AsyncStorageMixin, StorageMixin
from .wifi import AsyncWifiMixin, WifiMixin

logger = logging.getLogger(__name__)


class BusyBar(
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


class AsyncBusyBar(
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


__all__ = ["BusyBar", "AsyncBusyBar"]
