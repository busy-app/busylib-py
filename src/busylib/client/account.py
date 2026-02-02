from __future__ import annotations

import logging
from typing import Literal

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)

AccountProfileName = Literal["dev", "prod", "local", "custom"]


class AccountMixin(SyncClientBase):
    """
    Account linking and MQTT profile helpers.
    """

    def unlink_account(self) -> types.SuccessResponse:
        """
        Unlink the device from the account via DELETE /api/account.
        """
        logger.info("unlink_account")
        data = self._request("DELETE", "/api/account")
        return types.SuccessResponse.model_validate(data)

    def link_account(self) -> types.AccountLink:
        """
        Request an account link code via POST /api/account/link.
        """
        logger.info("link_account")
        data = self._request("POST", "/api/account/link")
        return types.AccountLink.model_validate(data)

    def get_account_info(self) -> types.AccountInfo:
        """
        Fetch linked account info via GET /api/account/info.
        """
        logger.info("get_account_info")
        data = self._request("GET", "/api/account/info")
        return types.AccountInfo.model_validate(data)

    def get_account_status(self) -> types.AccountState:
        """
        Fetch MQTT status info via GET /api/account/status.
        """
        logger.info("get_account_status")
        data = self._request("GET", "/api/account/status")
        return types.AccountState.model_validate(data)

    def get_account_profile(self) -> types.AccountProfile:
        """
        Fetch MQTT profile via GET /api/account/profile.
        """
        logger.info("get_account_profile")
        data = self._request("GET", "/api/account/profile")
        return types.AccountProfile.model_validate(data)

    def set_account_profile(
        self,
        profile: AccountProfileName,
        custom_url: str | None = None,
    ) -> types.SuccessResponse:
        """
        Set MQTT profile via POST /api/account/profile.
        """
        logger.info("set_account_profile profile=%s", profile)
        params: dict[str, str] = {"profile": profile}
        if custom_url:
            params["custom_url"] = custom_url
        data = self._request(
            "POST",
            "/api/account/profile",
            params=params,
        )
        return types.SuccessResponse.model_validate(data)


class AsyncAccountMixin(AsyncClientBase):
    """
    Async account linking and MQTT profile helpers.
    """

    async def unlink_account(self) -> types.SuccessResponse:
        """
        Unlink the device from the account via DELETE /api/account.
        """
        logger.info("async unlink_account")
        data = await self._request("DELETE", "/api/account")
        return types.SuccessResponse.model_validate(data)

    async def link_account(self) -> types.AccountLink:
        """
        Request an account link code via POST /api/account/link.
        """
        logger.info("async link_account")
        data = await self._request("POST", "/api/account/link")
        return types.AccountLink.model_validate(data)

    async def get_account_info(self) -> types.AccountInfo:
        """
        Fetch linked account info via GET /api/account/info.
        """
        logger.info("async get_account_info")
        data = await self._request("GET", "/api/account/info")
        return types.AccountInfo.model_validate(data)

    async def get_account_status(self) -> types.AccountState:
        """
        Fetch MQTT status info via GET /api/account/status.
        """
        logger.info("async get_account_status")
        data = await self._request("GET", "/api/account/status")
        return types.AccountState.model_validate(data)

    async def get_account_profile(self) -> types.AccountProfile:
        """
        Fetch MQTT profile via GET /api/account/profile.
        """
        logger.info("async get_account_profile")
        data = await self._request("GET", "/api/account/profile")
        return types.AccountProfile.model_validate(data)

    async def set_account_profile(
        self,
        profile: AccountProfileName,
        custom_url: str | None = None,
    ) -> types.SuccessResponse:
        """
        Set MQTT profile via POST /api/account/profile.
        """
        logger.info("async set_account_profile profile=%s", profile)
        params: dict[str, str] = {"profile": profile}
        if custom_url:
            params["custom_url"] = custom_url
        data = await self._request(
            "POST",
            "/api/account/profile",
            params=params,
        )
        return types.SuccessResponse.model_validate(data)
