from __future__ import annotations

import logging
from typing import Any

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class WifiMixin(SyncClientBase):
    """
    Wi-Fi control helpers: enable, connect, scan, and status.
    """

    def wifi_enable(self) -> types.SuccessResponse:
        logger.info("wifi_enable")
        data = self._request("POST", "/api/wifi/enable")
        return types.SuccessResponse.model_validate(data)

    def wifi_disable(self) -> types.SuccessResponse:
        logger.info("wifi_disable")
        data = self._request("POST", "/api/wifi/disable")
        return types.SuccessResponse.model_validate(data)

    def wifi_status(self) -> types.StatusResponse:
        logger.info("wifi_status")
        data = self._request("GET", "/api/wifi/status")
        return types.StatusResponse.model_validate(data)

    def wifi_connect(
        self, config: types.ConnectRequestConfig | dict[str, Any]
    ) -> types.SuccessResponse:
        ssid = (
            config.ssid
            if isinstance(config, types.ConnectRequestConfig)
            else config.get("ssid")
        )
        logger.info("wifi_connect ssid=%s", ssid)
        model = (
            config
            if isinstance(config, types.ConnectRequestConfig)
            else types.ConnectRequestConfig.model_validate(config)
        )
        payload = model.model_dump(exclude_none=True)
        data = self._request(
            "POST",
            "/api/wifi/connect",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

    def wifi_disconnect(self) -> types.SuccessResponse:
        logger.info("wifi_disconnect")
        data = self._request("POST", "/api/wifi/disconnect")
        return types.SuccessResponse.model_validate(data)

    def wifi_networks(self) -> types.NetworkResponse:
        logger.info("wifi_networks")
        data = self._request("GET", "/api/wifi/networks")
        return types.NetworkResponse.model_validate(data)


class AsyncWifiMixin(AsyncClientBase):
    """
    Async Wi-Fi control helpers: enable, connect, scan, and status.
    """

    async def wifi_enable(self) -> types.SuccessResponse:
        logger.info("async wifi_enable")
        data = await self._request("POST", "/api/wifi/enable")
        return types.SuccessResponse.model_validate(data)

    async def wifi_disable(self) -> types.SuccessResponse:
        logger.info("async wifi_disable")
        data = await self._request("POST", "/api/wifi/disable")
        return types.SuccessResponse.model_validate(data)

    async def wifi_status(self) -> types.StatusResponse:
        logger.info("async wifi_status")
        data = await self._request("GET", "/api/wifi/status")
        return types.StatusResponse.model_validate(data)

    async def wifi_connect(
        self,
        config: types.ConnectRequestConfig | dict[str, Any],
    ) -> types.SuccessResponse:
        ssid = (
            config.ssid
            if isinstance(config, types.ConnectRequestConfig)
            else config.get("ssid")
        )
        logger.info("async wifi_connect ssid=%s", ssid)
        model = (
            config
            if isinstance(config, types.ConnectRequestConfig)
            else types.ConnectRequestConfig.model_validate(config)
        )
        payload = model.model_dump(exclude_none=True)
        data = await self._request(
            "POST",
            "/api/wifi/connect",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

    async def wifi_disconnect(self) -> types.SuccessResponse:
        logger.info("async wifi_disconnect")
        data = await self._request("POST", "/api/wifi/disconnect")
        return types.SuccessResponse.model_validate(data)

    async def wifi_networks(self) -> types.NetworkResponse:
        logger.info("async wifi_networks")
        data = await self._request("GET", "/api/wifi/networks")
        return types.NetworkResponse.model_validate(data)
