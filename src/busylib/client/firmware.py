from __future__ import annotations

import logging

from .. import types, versioning
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class FirmwareMixin(SyncClientBase):
    """
    Version and system status methods.
    """

    def version(self) -> types.VersionInfo:
        logger.info("version")
        data = self._request("GET", "/api/version")
        version_info = types.VersionInfo.model_validate(data)
        if version_info.api_semver:
            self._device_api_version = version_info.api_semver
            versioning.ensure_compatible(
                library_version=self.api_version,
                device_version=version_info.api_semver,
            )
        return version_info

    def status(self) -> types.Status:
        logger.info("status")
        data = self._request("GET", "/api/status")
        return types.Status.model_validate(data)

    def status_system(self) -> types.StatusSystem:
        logger.info("status_system")
        data = self._request("GET", "/api/status/system")
        return types.StatusSystem.model_validate(data)

    def status_power(self) -> types.StatusPower:
        logger.info("status_power")
        data = self._request("GET", "/api/status/power")
        return types.StatusPower.model_validate(data)

    def name(self) -> types.DeviceNameResponse:
        """
        Fetch device name via GET /api/name.
        """
        logger.info("name")
        data = self._request("GET", "/api/name")
        return types.DeviceNameResponse.model_validate(data)

    def name_set(self, name: str) -> types.SuccessResponse:
        """
        Set device name via POST /api/name.
        """
        logger.info("name_set")
        payload = types.DeviceNameUpdate(name=name).model_dump()
        data = self._request(
            "POST",
            "/api/name",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

    def time(self) -> types.DeviceTimeResponse:
        """
        Fetch device time via GET /api/time.
        """
        logger.info("time")
        data = self._request("GET", "/api/time")
        return types.DeviceTimeResponse.model_validate(data)


class AsyncFirmwareMixin(AsyncClientBase):
    """
    Async variant of version and system status methods.
    """

    async def version(self) -> types.VersionInfo:
        logger.info("async version")
        data = await self._request("GET", "/api/version")
        version_info = types.VersionInfo.model_validate(data)
        if version_info.api_semver:
            self._device_api_version = version_info.api_semver
            versioning.ensure_compatible(
                library_version=self.api_version,
                device_version=version_info.api_semver,
            )
        return version_info

    async def status(self) -> types.Status:
        logger.info("async status")
        data = await self._request("GET", "/api/status")
        return types.Status.model_validate(data)

    async def status_system(self) -> types.StatusSystem:
        logger.info("async status_system")
        data = await self._request("GET", "/api/status/system")
        return types.StatusSystem.model_validate(data)

    async def status_power(self) -> types.StatusPower:
        logger.info("async status_power")
        data = await self._request("GET", "/api/status/power")
        return types.StatusPower.model_validate(data)

    async def name(self) -> types.DeviceNameResponse:
        """
        Fetch device name via GET /api/name.
        """
        logger.info("async name")
        data = await self._request("GET", "/api/name")
        return types.DeviceNameResponse.model_validate(data)

    async def name_set(self, name: str) -> types.SuccessResponse:
        """
        Set device name via POST /api/name.
        """
        logger.info("async name_set")
        payload = types.DeviceNameUpdate(name=name).model_dump()
        data = await self._request(
            "POST",
            "/api/name",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

    async def time(self) -> types.DeviceTimeResponse:
        """
        Fetch device time via GET /api/time.
        """
        logger.info("async time")
        data = await self._request("GET", "/api/time")
        return types.DeviceTimeResponse.model_validate(data)
