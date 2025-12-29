from __future__ import annotations

import logging
from typing import Any

from .base import AsyncClientBase, SyncClientBase
from .. import types

logger = logging.getLogger(__name__)


class WifiMixin(SyncClientBase):
    """
    Wi-Fi control helpers: enable, connect, scan, and status.
    """

    def enable_wifi(self) -> types.SuccessResponse:
        logger.info("enable_wifi")
        data = self._request("POST", "/api/wifi/enable")
        return types.SuccessResponse.model_validate(data)

    def disable_wifi(self) -> types.SuccessResponse:
        logger.info("disable_wifi")
        data = self._request("POST", "/api/wifi/disable")
        return types.SuccessResponse.model_validate(data)

    def get_wifi_status(self) -> types.StatusResponse:
        logger.info("get_wifi_status")
        data = self._request("GET", "/api/wifi/status")
        return types.StatusResponse.model_validate(data)

    def connect_wifi(self, config: types.ConnectRequestConfig | dict[str, Any]) -> types.SuccessResponse:
        ssid = config.ssid if isinstance(config, types.ConnectRequestConfig) else config.get("ssid")
        logger.info("connect_wifi ssid=%s", ssid)
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

    def disconnect_wifi(self) -> types.SuccessResponse:
        logger.info("disconnect_wifi")
        data = self._request("POST", "/api/wifi/disconnect")
        return types.SuccessResponse.model_validate(data)

    def scan_wifi_networks(self) -> types.NetworkResponse:
        logger.info("scan_wifi_networks")
        data = self._request("GET", "/api/wifi/networks")
        return types.NetworkResponse.model_validate(data)


class AsyncWifiMixin(AsyncClientBase):
    """
    Async Wi-Fi control helpers: enable, connect, scan, and status.
    """

    async def enable_wifi(self) -> types.SuccessResponse:
        logger.info("async enable_wifi")
        data = await self._request("POST", "/api/wifi/enable")
        return types.SuccessResponse.model_validate(data)

    async def disable_wifi(self) -> types.SuccessResponse:
        logger.info("async disable_wifi")
        data = await self._request("POST", "/api/wifi/disable")
        return types.SuccessResponse.model_validate(data)

    async def get_wifi_status(self) -> types.StatusResponse:
        logger.info("async get_wifi_status")
        data = await self._request("GET", "/api/wifi/status")
        return types.StatusResponse.model_validate(data)

    async def connect_wifi(
        self,
        config: types.ConnectRequestConfig | dict[str, Any],
    ) -> types.SuccessResponse:
        ssid = config.ssid if isinstance(config, types.ConnectRequestConfig) else config.get("ssid")
        logger.info("async connect_wifi ssid=%s", ssid)
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

    async def disconnect_wifi(self) -> types.SuccessResponse:
        logger.info("async disconnect_wifi")
        data = await self._request("POST", "/api/wifi/disconnect")
        return types.SuccessResponse.model_validate(data)

    async def scan_wifi_networks(self) -> types.NetworkResponse:
        logger.info("async scan_wifi_networks")
        data = await self._request("GET", "/api/wifi/networks")
        return types.NetworkResponse.model_validate(data)
