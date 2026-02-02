from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class BleMixin(SyncClientBase):
    """
    BLE control helpers.
    """

    def ble_enable(self) -> types.SuccessResponse:
        logger.info("ble_enable")
        data = self._request("POST", "/api/ble/enable")
        return types.SuccessResponse.model_validate(data)

    def ble_disable(self) -> types.SuccessResponse:
        logger.info("ble_disable")
        data = self._request("POST", "/api/ble/disable")
        return types.SuccessResponse.model_validate(data)

    def ble_status(self) -> types.BleStatus:
        logger.info("ble_status")
        data = self._request("GET", "/api/ble/status")
        return types.BleStatus.model_validate(data)

    def ble_forget_pairing(self) -> types.SuccessResponse:
        logger.info("ble_forget_pairing")
        data = self._request("DELETE", "/api/ble/pairing")
        return types.SuccessResponse.model_validate(data)


class AsyncBleMixin(AsyncClientBase):
    """
    Async BLE control helpers.
    """

    async def ble_enable(self) -> types.SuccessResponse:
        logger.info("async ble_enable")
        data = await self._request("POST", "/api/ble/enable")
        return types.SuccessResponse.model_validate(data)

    async def ble_disable(self) -> types.SuccessResponse:
        logger.info("async ble_disable")
        data = await self._request("POST", "/api/ble/disable")
        return types.SuccessResponse.model_validate(data)

    async def ble_status(self) -> types.BleStatus:
        logger.info("async ble_status")
        data = await self._request("GET", "/api/ble/status")
        return types.BleStatus.model_validate(data)

    async def ble_forget_pairing(self) -> types.SuccessResponse:
        logger.info("async ble_forget_pairing")
        data = await self._request("DELETE", "/api/ble/pairing")
        return types.SuccessResponse.model_validate(data)
