from __future__ import annotations

import logging
from typing import Any

from .. import types, versioning
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class WifiMixin(SyncClientBase):
    """
    Wi-Fi control helpers: connect, disconnect, scan, and status.
    """

    @versioning.removed_endpoint(
        # Last served by firmware 0.2.0 (API 0.0.0); gone since 0.3.0.
        path="/api/wifi/enable",
        method="POST",
        replacement="wifi_connect() / wifi_disconnect()",
    )
    def wifi_enable(self) -> types.SuccessResponse:
        """
        Removed from the device API.

        No supported firmware serves POST /api/wifi/enable, so calling this raises
        `BusyBarRemovedEndpointError`. Use `wifi_connect() / wifi_disconnect()` instead.
        """
        # Unreachable: the decorator raises before the body runs.
        ...

    @versioning.removed_endpoint(
        path="/api/wifi/disable",
        method="POST",
        replacement="wifi_connect() / wifi_disconnect()",
    )
    def wifi_disable(self) -> types.SuccessResponse:
        """
        Removed from the device API.

        No supported firmware serves POST /api/wifi/disable, so calling this raises
        `BusyBarRemovedEndpointError`. Use `wifi_connect() / wifi_disconnect()` instead.
        """
        # Unreachable: the decorator raises before the body runs.
        ...

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
        """
        Scan for nearby networks via GET /api/wifi/networks.

        The device cannot scan while it is associated: doing so returns
        `400 "Scan not possible when connected"` as a `BusyBarAPIError`.
        Disconnect first with `wifi_disconnect()`, or skip the scan and pass
        the SSID to `wifi_connect()` directly.
        """
        logger.info("wifi_networks")
        data = self._request("GET", "/api/wifi/networks")
        return types.NetworkResponse.model_validate(data)


class AsyncWifiMixin(AsyncClientBase):
    """
    Async Wi-Fi control helpers: connect, disconnect, scan, and status.
    """

    @versioning.removed_endpoint(
        # Last served by firmware 0.2.0 (API 0.0.0); gone since 0.3.0.
        path="/api/wifi/enable",
        method="POST",
        replacement="wifi_connect() / wifi_disconnect()",
    )
    async def wifi_enable(self) -> types.SuccessResponse:
        """
        Removed from the device API.

        No supported firmware serves POST /api/wifi/enable, so calling this raises
        `BusyBarRemovedEndpointError`. Use `wifi_connect() / wifi_disconnect()` instead.
        """
        # Unreachable: the decorator raises before the body runs.
        ...

    @versioning.removed_endpoint(
        path="/api/wifi/disable",
        method="POST",
        replacement="wifi_connect() / wifi_disconnect()",
    )
    async def wifi_disable(self) -> types.SuccessResponse:
        """
        Removed from the device API.

        No supported firmware serves POST /api/wifi/disable, so calling this raises
        `BusyBarRemovedEndpointError`. Use `wifi_connect() / wifi_disconnect()` instead.
        """
        # Unreachable: the decorator raises before the body runs.
        ...

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
        """
        Scan for nearby networks via GET /api/wifi/networks.

        The device cannot scan while it is associated: doing so returns
        `400 "Scan not possible when connected"` as a `BusyBarAPIError`.
        Disconnect first with `wifi_disconnect()`, or skip the scan and pass
        the SSID to `wifi_connect()` directly.
        """
        logger.info("async wifi_networks")
        data = await self._request("GET", "/api/wifi/networks")
        return types.NetworkResponse.model_validate(data)
