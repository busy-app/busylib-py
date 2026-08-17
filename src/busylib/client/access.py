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

    def access_tokens_list(self) -> types.AccessTokensInfo:
        """
        List issued access tokens via GET /api/access/tokens.

        The secret itself is returned only when a token is minted, so every
        token here has `token` set to None.
        """
        logger.info("access_tokens_list")
        data = self._request("GET", "/api/access/tokens")
        return types.AccessTokensInfo.model_validate(data)

    def access_token_mint(self, name: str) -> types.AccessToken:
        """
        Issue a new access token via POST /api/access/tokens.

        This is the only time the device discloses the secret; it cannot be
        read back afterwards.
        """
        logger.info("access_token_mint name=%s", name)
        payload = types.AccessTokenMintRequest(name=name).model_dump()
        data = self._request("POST", "/api/access/tokens", json_payload=payload)
        return types.AccessToken.model_validate(data)

    def access_tokens_delete_all(self) -> types.SuccessResponse:
        """
        Revoke every access token via DELETE /api/access/tokens.
        """
        logger.info("access_tokens_delete_all")
        data = self._request("DELETE", "/api/access/tokens")
        return types.SuccessResponse.model_validate(data)

    def access_tokens_revoke(self, short_id: str) -> types.SuccessResponse:
        """
        Revoke one access token via DELETE /api/access/tokens/{short_id}.
        """
        logger.info("access_tokens_revoke short_id=%s", short_id)
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

    async def access_tokens_list(self) -> types.AccessTokensInfo:
        """
        List issued access tokens via GET /api/access/tokens.

        The secret itself is returned only when a token is minted, so every
        token here has `token` set to None.
        """
        logger.info("async access_tokens_list")
        data = await self._request("GET", "/api/access/tokens")
        return types.AccessTokensInfo.model_validate(data)

    async def access_token_mint(self, name: str) -> types.AccessToken:
        """
        Issue a new access token via POST /api/access/tokens.

        This is the only time the device discloses the secret; it cannot be
        read back afterwards.
        """
        logger.info("async access_token_mint name=%s", name)
        payload = types.AccessTokenMintRequest(name=name).model_dump()
        data = await self._request("POST", "/api/access/tokens", json_payload=payload)
        return types.AccessToken.model_validate(data)

    async def access_tokens_delete_all(self) -> types.SuccessResponse:
        """
        Revoke every access token via DELETE /api/access/tokens.
        """
        logger.info("async access_tokens_delete_all")
        data = await self._request("DELETE", "/api/access/tokens")
        return types.SuccessResponse.model_validate(data)

    async def access_tokens_revoke(self, short_id: str) -> types.SuccessResponse:
        """
        Revoke one access token via DELETE /api/access/tokens/{short_id}.
        """
        logger.info("async access_tokens_revoke short_id=%s", short_id)
        data = await self._request("DELETE", f"/api/access/tokens/{short_id}")
        return types.SuccessResponse.model_validate(data)
