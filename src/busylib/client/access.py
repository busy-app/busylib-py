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

    def access(self) -> types.HttpAccessInfo:
        """
        Fetch HTTP access mode via GET /api/access.
        """
        logger.info("access")
        data = self._request("GET", "/api/access")
        return types.HttpAccessInfo.model_validate(data)

    def access_set(self, mode: HttpAccessMode, key: str) -> types.SuccessResponse:
        """
        Set HTTP access mode via POST /api/access.
        """
        logger.info("access_set mode=%s", mode)
        params = {"mode": mode, "key": key}
        data = self._request("POST", "/api/access", params=params)
        return types.SuccessResponse.model_validate(data)

    def tokens_list(self) -> types.AccessTokensInfo:
        logger.info("tokens_list")
        data = self._request("GET", "/api/access/tokens")
        return types.AccessTokensInfo.model_validate(data)

    def token_mint(self, name: str) -> types.AccessToken:
        logger.info("token_mint name=%s", name)
        payload = types.AccessTokenMintRequest(name=name).model_dump()
        data = self._request("POST", "/api/access/tokens", json_payload=payload)
        return types.AccessToken.model_validate(data)

    def tokens_delete_all(self) -> types.SuccessResponse:
        logger.info("tokens_delete")
        data = self._request("DELETE", "/api/access/tokens")
        return types.SuccessResponse.model_validate(data)

    def tokens_revoke(self, short_id: str) -> types.SuccessResponse:
        logger.info("tokens_revoke short_id=%s", short_id)
        data = self._request("DELETE", f"/api/access/tokens/{short_id}")
        return types.SuccessResponse.model_validate(data)


class AsyncAccessMixin(AsyncClientBase):
    """
    Async HTTP access mode helpers.
    """

    async def access(self) -> types.HttpAccessInfo:
        """
        Fetch HTTP access mode via GET /api/access.
        """
        logger.info("async access")
        data = await self._request("GET", "/api/access")
        return types.HttpAccessInfo.model_validate(data)

    async def access_set(self, mode: HttpAccessMode, key: str) -> types.SuccessResponse:
        """
        Set HTTP access mode via POST /api/access.
        """
        logger.info("async access_set mode=%s", mode)
        params = {"mode": mode, "key": key}
        data = await self._request("POST", "/api/access", params=params)
        return types.SuccessResponse.model_validate(data)

    async def tokens_list(self) -> types.AccessTokensInfo:
        logger.info("tokens_list")
        data = await self._request("GET", "/api/access/tokens")
        return types.AccessTokensInfo.model_validate(data)

    async def token_mint(self, name: str) -> types.AccessToken:
        logger.info("token_mint name=%s", name)
        payload = types.AccessTokenMintRequest(name=name).model_dump()
        data = await self._request("POST", "/api/access/tokens", json_payload=payload)
        return types.AccessToken.model_validate(data)

    async def tokens_delete_all(self) -> types.SuccessResponse:
        logger.info("tokens_delete")
        data = await self._request("DELETE", "/api/access/tokens")
        return types.SuccessResponse.model_validate(data)

    async def tokens_revoke(self, short_id: str) -> types.SuccessResponse:
        logger.info("tokens_revoke short_id=%s", short_id)
        data = await self._request("DELETE", f"/api/access/tokens/{short_id}")
        return types.SuccessResponse.model_validate(data)
