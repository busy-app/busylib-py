from __future__ import annotations

import logging

import httpx

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)
ASSET_UPLOAD_TIMEOUT = httpx.Timeout(
    120.0,
    connect=5.0,
    read=120.0,
    write=120.0,
    pool=5.0,
)


class AssetsMixin(SyncClientBase):
    """
    Asset upload and deletion helpers.
    """

    def assets_upload(
        self,
        application_name: str,
        filename: str,
        data: bytes,
        *,
        timeout: float | httpx.Timeout | None = ASSET_UPLOAD_TIMEOUT,
    ) -> types.SuccessResponse:
        """
        Upload an asset file for the given application.

        Uses a longer default timeout to tolerate large payload uploads.
        """
        logger.info(
            "assets_upload application_name=%s filename=%s size=%s",
            application_name,
            filename,
            len(data),
        )
        payload = self._request(
            "POST",
            "/api/assets/upload",
            params={"file": filename},
            application_name=application_name,
            data=data,
            timeout=timeout,
        )
        return types.SuccessResponse.model_validate(payload)

    def assets_delete(self, application_name: str) -> types.SuccessResponse:
        logger.info("assets_delete application_name=%s", application_name)
        data = self._request(
            "DELETE",
            "/api/assets/upload",
            application_name=application_name,
        )
        return types.SuccessResponse.model_validate(data)


class AsyncAssetsMixin(AsyncClientBase):
    """
    Async asset upload and deletion helpers.
    """

    async def assets_upload(
        self,
        application_name: str,
        filename: str,
        data: bytes,
        *,
        timeout: float | httpx.Timeout | None = ASSET_UPLOAD_TIMEOUT,
    ) -> types.SuccessResponse:
        """
        Upload an asset file for the given application.

        Uses a longer default timeout to tolerate large payload uploads.
        """
        logger.info(
            "async assets_upload application_name=%s filename=%s size=%s",
            application_name,
            filename,
            len(data),
        )
        payload = await self._request(
            "POST",
            "/api/assets/upload",
            params={"file": filename},
            application_name=application_name,
            data=data,
            timeout=timeout,
        )
        return types.SuccessResponse.model_validate(payload)

    async def assets_delete(self, application_name: str) -> types.SuccessResponse:
        logger.info("async assets_delete application_name=%s", application_name)
        data = await self._request(
            "DELETE",
            "/api/assets/upload",
            application_name=application_name,
        )
        return types.SuccessResponse.model_validate(data)
