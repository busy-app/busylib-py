from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class UpdaterMixin(SyncClientBase):
    """
    Firmware update helpers for the updater API.
    """

    def update(
        self,
        firmware_data: bytes,
    ) -> types.SuccessResponse:
        """
        Upload firmware update TAR and initiate update.
        """
        logger.info("update size=%s", len(firmware_data))
        data = self._request(
            "POST",
            "/api/update",
            data=firmware_data,
        )
        return types.SuccessResponse.model_validate(data)

    def update_check(self) -> types.SuccessResponse:
        """
        Start asynchronous firmware update check.
        """
        logger.info("update_check")
        data = self._request("POST", "/api/update/check")
        return types.SuccessResponse.model_validate(data)

    def update_status(self) -> types.UpdateStatus:
        """
        Get firmware update status with progress information.
        """
        logger.info("update_status")
        data = self._request("GET", "/api/update/status")
        return types.UpdateStatus.model_validate(data)

    def update_changelog(self, version: str) -> types.UpdateChangelogResponse:
        """
        Fetch update changelog for a specific version.
        """
        logger.info("update_changelog version=%s", version)
        data = self._request(
            "GET",
            "/api/update/changelog",
            params={"version": version},
        )
        return types.UpdateChangelogResponse.model_validate(data)

    def update_install(self, version: str) -> types.SuccessResponse:
        """
        Start firmware update installation by version.
        """
        logger.info("update_install version=%s", version)
        data = self._request(
            "POST",
            "/api/update/install",
            params={"version": version},
        )
        return types.SuccessResponse.model_validate(data)

    def update_abort_download(self) -> types.SuccessResponse:
        """
        Abort an ongoing firmware download.
        """
        logger.info("update_abort_download")
        data = self._request("POST", "/api/update/abort_download")
        return types.SuccessResponse.model_validate(data)


class AsyncUpdaterMixin(AsyncClientBase):
    """
    Async firmware update helpers for the updater API.
    """

    async def update(
        self,
        firmware_data: bytes,
    ) -> types.SuccessResponse:
        """
        Upload firmware update TAR and initiate update.
        """
        logger.info("async update size=%s", len(firmware_data))
        data = await self._request(
            "POST",
            "/api/update",
            data=firmware_data,
        )
        return types.SuccessResponse.model_validate(data)

    async def update_check(self) -> types.SuccessResponse:
        """
        Start asynchronous firmware update check.
        """
        logger.info("async update_check")
        data = await self._request("POST", "/api/update/check")
        return types.SuccessResponse.model_validate(data)

    async def update_status(self) -> types.UpdateStatus:
        """
        Get firmware update status with progress information.
        """
        logger.info("async update_status")
        data = await self._request("GET", "/api/update/status")
        return types.UpdateStatus.model_validate(data)

    async def update_changelog(self, version: str) -> types.UpdateChangelogResponse:
        """
        Fetch update changelog for a specific version.
        """
        logger.info("async update_changelog version=%s", version)
        data = await self._request(
            "GET",
            "/api/update/changelog",
            params={"version": version},
        )
        return types.UpdateChangelogResponse.model_validate(data)

    async def update_install(self, version: str) -> types.SuccessResponse:
        """
        Start firmware update installation by version.
        """
        logger.info("async update_install version=%s", version)
        data = await self._request(
            "POST",
            "/api/update/install",
            params={"version": version},
        )
        return types.SuccessResponse.model_validate(data)

    async def update_abort_download(self) -> types.SuccessResponse:
        """
        Abort an ongoing firmware download.
        """
        logger.info("async update_abort_download")
        data = await self._request("POST", "/api/update/abort_download")
        return types.SuccessResponse.model_validate(data)
