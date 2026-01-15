from __future__ import annotations

import logging
from typing import Any

from .. import types, versioning
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class FirmwareMixin(SyncClientBase):
    """
    Version, firmware update, and system status methods.
    """

    def get_version(self) -> types.VersionInfo:
        logger.info("get_version")
        data = self._request("GET", "/api/version")
        version_info = types.VersionInfo.model_validate(data)
        if version_info.api_semver:
            self._device_api_version = version_info.api_semver
            versioning.ensure_compatible(
                library_version=self.api_version,
                device_version=version_info.api_semver,
            )
        return version_info

    def update_firmware(
        self,
        firmware_data: bytes,
        name: str | None = None,
    ) -> types.SuccessResponse:
        logger.info("update_firmware name=%s size=%s", name, len(firmware_data))
        params: dict[str, Any] = {}
        if name:
            params["name"] = name

        data = self._request(
            "POST",
            "/api/update",
            params=params or None,
            data=firmware_data,
        )
        return types.SuccessResponse.model_validate(data)

    def get_status(self) -> types.Status:
        logger.info("get_status")
        data = self._request("GET", "/api/status")
        return types.Status.model_validate(data)

    def get_system_status(self) -> types.StatusSystem:
        logger.info("get_system_status")
        data = self._request("GET", "/api/status/system")
        return types.StatusSystem.model_validate(data)

    def get_power_status(self) -> types.StatusPower:
        logger.info("get_power_status")
        data = self._request("GET", "/api/status/power")
        return types.StatusPower.model_validate(data)

    def get_device_name(self) -> types.DeviceNameResponse:
        """
        Fetch device name via GET /api/name.
        """
        logger.info("get_device_name")
        data = self._request("GET", "/api/name")
        return types.DeviceNameResponse.model_validate(data)

    def get_device_time(self) -> types.DeviceTimeResponse:
        """
        Fetch device time via GET /api/time.
        """
        logger.info("get_device_time")
        data = self._request("GET", "/api/time")
        return types.DeviceTimeResponse.model_validate(data)


class AsyncFirmwareMixin(AsyncClientBase):
    """
    Async variant of version, firmware update, and system status methods.
    """

    async def get_version(self) -> types.VersionInfo:
        logger.info("async get_version")
        data = await self._request("GET", "/api/version")
        version_info = types.VersionInfo.model_validate(data)
        if version_info.api_semver:
            self._device_api_version = version_info.api_semver
            versioning.ensure_compatible(
                library_version=self.api_version,
                device_version=version_info.api_semver,
            )
        return version_info

    async def update_firmware(
        self,
        firmware_data: bytes,
        name: str | None = None,
    ) -> types.SuccessResponse:
        logger.info("async update_firmware name=%s size=%s", name, len(firmware_data))
        params: dict[str, Any] = {}
        if name:
            params["name"] = name

        data = await self._request(
            "POST",
            "/api/update",
            params=params or None,
            data=firmware_data,
        )
        return types.SuccessResponse.model_validate(data)

    async def get_status(self) -> types.Status:
        logger.info("async get_status")
        data = await self._request("GET", "/api/status")
        return types.Status.model_validate(data)

    async def get_system_status(self) -> types.StatusSystem:
        logger.info("async get_system_status")
        data = await self._request("GET", "/api/status/system")
        return types.StatusSystem.model_validate(data)

    async def get_power_status(self) -> types.StatusPower:
        logger.info("async get_power_status")
        data = await self._request("GET", "/api/status/power")
        return types.StatusPower.model_validate(data)

    async def get_device_name(self) -> types.DeviceNameResponse:
        """
        Fetch device name via GET /api/name.
        """
        logger.info("async get_device_name")
        data = await self._request("GET", "/api/name")
        return types.DeviceNameResponse.model_validate(data)

    async def get_device_time(self) -> types.DeviceTimeResponse:
        """
        Fetch device time via GET /api/time.
        """
        logger.info("async get_device_time")
        data = await self._request("GET", "/api/time")
        return types.DeviceTimeResponse.model_validate(data)
