from __future__ import annotations

import logging
from typing import Literal

from .. import types, versioning
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)

AccountProfileName = Literal["dev", "prod", "local", "custom"]


class AccountMixin(SyncClientBase):
    """
    Account linking and MQTT backend helpers.
    """

    @versioning.requires_openapi(
        "1.0.0",
        path="/api/account",
        method="DELETE",
    )
    def account_unlink(self) -> types.SuccessResponse:
        """
        Unlink the device from the account via DELETE /api/account.
        """
        logger.info("account_unlink")
        data = self._request("DELETE", "/api/account")
        return types.SuccessResponse.model_validate(data)

    @versioning.requires_openapi(
        "1.0.0",
        path="/api/account/link",
        method="POST",
    )
    def account_link(self) -> types.AccountLink:
        """
        Request an account link code via POST /api/account/link.
        """
        logger.info("account_link")
        data = self._request("POST", "/api/account/link")
        return types.AccountLink.model_validate(data)

    @versioning.requires_openapi(
        "4.1.0",
        path="/api/account/info",
        method="GET",
    )
    def account_info(self) -> types.AccountInfo:
        """
        Fetch linked account info via GET /api/account/info.
        """
        logger.info("account_info")
        data = self._request("GET", "/api/account/info")
        return types.AccountInfo.model_validate(data)

    @versioning.requires_openapi(
        "4.1.0",
        path="/api/account/status",
        method="GET",
    )
    def account_status(self) -> types.AccountState:
        """
        Fetch MQTT status info via GET /api/account/status.
        """
        logger.info("account_status")
        data = self._request("GET", "/api/account/status")
        return types.AccountState.model_validate(data)

    @versioning.requires_openapi(
        "23.0.0",
        path="/api/account/backend",
        method="GET",
    )
    def account_backend(self) -> types.AccountBackend:
        """
        Fetch MQTT backend settings via GET /api/account/backend.
        """
        logger.info("account_backend")
        data = self._request("GET", "/api/account/backend")
        return types.AccountBackend.model_validate(data)

    @versioning.requires_openapi(
        "23.0.0",
        path="/api/account/backend",
        method="PUT",
    )
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

    @versioning.removed_endpoint(
        # Served by firmware 0.6.0-rc..0.8.1 (API 4.1.0..18.3.0); gone since 0.9.0-rc.
        path="/api/account/profile",
        method="GET",
        replacement="account_backend()",
    )
    def account_profile(self) -> types.AccountProfile:
        """
        Removed from the device API.

        No supported firmware serves GET /api/account/profile, so calling this raises
        `BusyBarRemovedEndpointError`. Use `account_backend()` instead.
        """
        # Unreachable: the decorator raises before the body runs.
        ...

    @versioning.removed_endpoint(
        # Served by firmware 0.6.0-rc..0.8.1 (API 4.1.0..18.3.0); gone since 0.9.0-rc.
        path="/api/account/profile",
        method="POST",
        replacement="account_backend_set()",
    )
    def account_profile_set(
        self,
        profile: AccountProfileName,
        custom_url: str | None = None,
    ) -> types.SuccessResponse:
        """
        Removed from the device API.

        No supported firmware serves POST /api/account/profile, so calling this raises
        `BusyBarRemovedEndpointError`. Use `account_backend_set()` instead.
        """
        # Unreachable: the decorator raises before the body runs.
        ...


class AsyncAccountMixin(AsyncClientBase):
    """
    Async account linking and MQTT backend helpers.
    """

    @versioning.requires_openapi(
        "1.0.0",
        path="/api/account",
        method="DELETE",
    )
    async def account_unlink(self) -> types.SuccessResponse:
        """
        Unlink the device from the account via DELETE /api/account.
        """
        logger.info("async account_unlink")
        data = await self._request("DELETE", "/api/account")
        return types.SuccessResponse.model_validate(data)

    @versioning.requires_openapi(
        "1.0.0",
        path="/api/account/link",
        method="POST",
    )
    async def account_link(self) -> types.AccountLink:
        """
        Request an account link code via POST /api/account/link.
        """
        logger.info("async account_link")
        data = await self._request("POST", "/api/account/link")
        return types.AccountLink.model_validate(data)

    @versioning.requires_openapi(
        "4.1.0",
        path="/api/account/info",
        method="GET",
    )
    async def account_info(self) -> types.AccountInfo:
        """
        Fetch linked account info via GET /api/account/info.
        """
        logger.info("async account_info")
        data = await self._request("GET", "/api/account/info")
        return types.AccountInfo.model_validate(data)

    @versioning.requires_openapi(
        "4.1.0",
        path="/api/account/status",
        method="GET",
    )
    async def account_status(self) -> types.AccountState:
        """
        Fetch MQTT status info via GET /api/account/status.
        """
        logger.info("async account_status")
        data = await self._request("GET", "/api/account/status")
        return types.AccountState.model_validate(data)

    @versioning.requires_openapi(
        "23.0.0",
        path="/api/account/backend",
        method="GET",
    )
    async def account_backend(self) -> types.AccountBackend:
        """
        Fetch MQTT backend settings via GET /api/account/backend.
        """
        logger.info("async account_backend")
        data = await self._request("GET", "/api/account/backend")
        return types.AccountBackend.model_validate(data)

    @versioning.requires_openapi(
        "23.0.0",
        path="/api/account/backend",
        method="PUT",
    )
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

    @versioning.removed_endpoint(
        # Served by firmware 0.6.0-rc..0.8.1 (API 4.1.0..18.3.0); gone since 0.9.0-rc.
        path="/api/account/profile",
        method="GET",
        replacement="account_backend()",
    )
    async def account_profile(self) -> types.AccountProfile:
        """
        Removed from the device API.

        No supported firmware serves GET /api/account/profile, so calling this raises
        `BusyBarRemovedEndpointError`. Use `account_backend()` instead.
        """
        # Unreachable: the decorator raises before the body runs.
        ...

    @versioning.removed_endpoint(
        # Served by firmware 0.6.0-rc..0.8.1 (API 4.1.0..18.3.0); gone since 0.9.0-rc.
        path="/api/account/profile",
        method="POST",
        replacement="account_backend_set()",
    )
    async def account_profile_set(
        self,
        profile: AccountProfileName,
        custom_url: str | None = None,
    ) -> types.SuccessResponse:
        """
        Removed from the device API.

        No supported firmware serves POST /api/account/profile, so calling this raises
        `BusyBarRemovedEndpointError`. Use `account_backend_set()` instead.
        """
        # Unreachable: the decorator raises before the body runs.
        ...
