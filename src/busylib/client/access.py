from __future__ import annotations

import logging
from typing import Literal

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)

HttpAccessMode = Literal["disabled", "enabled", "key"]


class AccessMixin(SyncClientBase):
    """
    HTTP access mode helpers.
    """

    def get_http_access(self) -> types.HttpAccessInfo:
        """
        Fetch HTTP access mode via GET /api/access.
        """
        logger.info("get_http_access")
        data = self._request("GET", "/api/access")
        return types.HttpAccessInfo.model_validate(data)

    def set_http_access(self, mode: HttpAccessMode, key: str) -> types.SuccessResponse:
        """
        Set HTTP access mode via POST /api/access.
        """
        logger.info("set_http_access mode=%s", mode)
        params = {"mode": mode, "key": key}
        data = self._request("POST", "/api/access", params=params)
        return types.SuccessResponse.model_validate(data)


class AsyncAccessMixin(AsyncClientBase):
    """
    Async HTTP access mode helpers.
    """

    async def get_http_access(self) -> types.HttpAccessInfo:
        """
        Fetch HTTP access mode via GET /api/access.
        """
        logger.info("async get_http_access")
        data = await self._request("GET", "/api/access")
        return types.HttpAccessInfo.model_validate(data)

    async def set_http_access(
        self, mode: HttpAccessMode, key: str
    ) -> types.SuccessResponse:
        """
        Set HTTP access mode via POST /api/access.
        """
        logger.info("async set_http_access mode=%s", mode)
        params = {"mode": mode, "key": key}
        data = await self._request("POST", "/api/access", params=params)
        return types.SuccessResponse.model_validate(data)
