from __future__ import annotations

import logging
from typing import Literal

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)

AccountProfileName = Literal["dev", "prod", "local", "custom"]


class AccountMixin(SyncClientBase):
    """
    Account linking and MQTT backend helpers.
    """

    def account_unlink(self) -> types.SuccessResponse:
        """
        Unlink the device from the account via DELETE /api/account.
        """
        logger.info("account_unlink")
        data = self._request("DELETE", "/api/account")
        return types.SuccessResponse.model_validate(data)

    def account_link(self) -> types.AccountLink:
        """
        Request an account link code via POST /api/account/link.
        """
        logger.info("account_link")
        data = self._request("POST", "/api/account/link")
        return types.AccountLink.model_validate(data)

    def account_info(self) -> types.AccountInfo:
        """
        Fetch linked account info via GET /api/account/info.
        """
        logger.info("account_info")
        data = self._request("GET", "/api/account/info")
        return types.AccountInfo.model_validate(data)

    def account_status(self) -> types.AccountState:
        """
        Fetch MQTT status info via GET /api/account/status.
        """
        logger.info("account_status")
        data = self._request("GET", "/api/account/status")
        return types.AccountState.model_validate(data)

    def account_backend(self) -> types.AccountBackend:
        """
        Fetch MQTT backend settings via GET /api/account/backend.
        """
        logger.info("account_backend")
        data = self._request("GET", "/api/account/backend")
        return types.AccountBackend.model_validate(data)

    def account_backend_set(
        self,
        backend: types.AccountBackend | dict[str, object],
    ) -> types.SuccessResponse:
        """
        Set MQTT backend settings via PUT /api/account/backend.
        """
        logger.info("account_backend_set")
        model = (
            backend
            if isinstance(backend, types.AccountBackend)
            else types.AccountBackend.model_validate(backend)
        )
        data = self._request(
            "PUT",
            "/api/account/backend",
            json_payload=model.model_dump(mode="json"),
        )
        return types.SuccessResponse.model_validate(data)

    def account_profile(self) -> types.AccountProfile:
        """
        Fetch legacy MQTT profile via GET /api/account/profile.
        """
        logger.info("account_profile")
        data = self._request("GET", "/api/account/profile")
        return types.AccountProfile.model_validate(data)

    def account_profile_set(
        self,
        profile: AccountProfileName,
        custom_url: str | None = None,
    ) -> types.SuccessResponse:
        """
        Set legacy MQTT profile via POST /api/account/profile.
        """
        logger.info("account_profile_set profile=%s", profile)
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
    Async account linking and MQTT backend helpers.
    """

    async def account_unlink(self) -> types.SuccessResponse:
        """
        Unlink the device from the account via DELETE /api/account.
        """
        logger.info("async account_unlink")
        data = await self._request("DELETE", "/api/account")
        return types.SuccessResponse.model_validate(data)

    async def account_link(self) -> types.AccountLink:
        """
        Request an account link code via POST /api/account/link.
        """
        logger.info("async account_link")
        data = await self._request("POST", "/api/account/link")
        return types.AccountLink.model_validate(data)

    async def account_info(self) -> types.AccountInfo:
        """
        Fetch linked account info via GET /api/account/info.
        """
        logger.info("async account_info")
        data = await self._request("GET", "/api/account/info")
        return types.AccountInfo.model_validate(data)

    async def account_status(self) -> types.AccountState:
        """
        Fetch MQTT status info via GET /api/account/status.
        """
        logger.info("async account_status")
        data = await self._request("GET", "/api/account/status")
        return types.AccountState.model_validate(data)

    async def account_backend(self) -> types.AccountBackend:
        """
        Fetch MQTT backend settings via GET /api/account/backend.
        """
        logger.info("async account_backend")
        data = await self._request("GET", "/api/account/backend")
        return types.AccountBackend.model_validate(data)

    async def account_backend_set(
        self,
        backend: types.AccountBackend | dict[str, object],
    ) -> types.SuccessResponse:
        """
        Set MQTT backend settings via PUT /api/account/backend.
        """
        logger.info("async account_backend_set")
        model = (
            backend
            if isinstance(backend, types.AccountBackend)
            else types.AccountBackend.model_validate(backend)
        )
        data = await self._request(
            "PUT",
            "/api/account/backend",
            json_payload=model.model_dump(mode="json"),
        )
        return types.SuccessResponse.model_validate(data)

    async def account_profile(self) -> types.AccountProfile:
        """
        Fetch legacy MQTT profile via GET /api/account/profile.
        """
        logger.info("async account_profile")
        data = await self._request("GET", "/api/account/profile")
        return types.AccountProfile.model_validate(data)

    async def account_profile_set(
        self,
        profile: AccountProfileName,
        custom_url: str | None = None,
    ) -> types.SuccessResponse:
        """
        Set legacy MQTT profile via POST /api/account/profile.
        """
        logger.info("async account_profile_set profile=%s", profile)
        params: dict[str, str] = {"profile": profile}
        if custom_url:
            params["custom_url"] = custom_url
        data = await self._request(
            "POST",
            "/api/account/profile",
            params=params,
        )
        return types.SuccessResponse.model_validate(data)
