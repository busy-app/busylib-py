from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class AssetsMixin(SyncClientBase):
    """
    Asset upload and deletion helpers.
    """

    def upload_asset(
        self, app_id: str, filename: str, data: bytes
    ) -> types.SuccessResponse:
        logger.info(
            "upload_asset app_id=%s filename=%s size=%s", app_id, filename, len(data)
        )
        payload = self._request(
            "POST",
            "/api/assets/upload",
            params={"app_id": app_id, "file": filename},
            data=data,
        )
        return types.SuccessResponse.model_validate(payload)

    def delete_app_assets(self, app_id: str) -> types.SuccessResponse:
        logger.info("delete_app_assets app_id=%s", app_id)
        data = self._request(
            "DELETE",
            "/api/assets/upload",
            params={"app_id": app_id},
        )
        return types.SuccessResponse.model_validate(data)


class AsyncAssetsMixin(AsyncClientBase):
    """
    Async asset upload and deletion helpers.
    """

    async def upload_asset(
        self, app_id: str, filename: str, data: bytes
    ) -> types.SuccessResponse:
        logger.info(
            "async upload_asset app_id=%s filename=%s size=%s",
            app_id,
            filename,
            len(data),
        )
        payload = await self._request(
            "POST",
            "/api/assets/upload",
            params={"app_id": app_id, "file": filename},
            data=data,
        )
        return types.SuccessResponse.model_validate(payload)

    async def delete_app_assets(self, app_id: str) -> types.SuccessResponse:
        logger.info("async delete_app_assets app_id=%s", app_id)
        data = await self._request(
            "DELETE",
            "/api/assets/upload",
            params={"app_id": app_id},
        )
        return types.SuccessResponse.model_validate(data)
