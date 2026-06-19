from __future__ import annotations

import logging
from typing import Literal

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class SmartHomeMixin(SyncClientBase):
    """
    Smart home pairing and switch helpers.
    """

    def smart_home_pairing(self) -> types.SmartHomePairingInfo:
        """
        Fetch smart home pairing status via GET /api/smart_home/pairing.
        """
        logger.info("smart_home_pairing")
        data = self._request("GET", "/api/smart_home/pairing")
        return types.SmartHomePairingInfo.model_validate(data)

    def smart_home_pairing_start(self) -> types.SmartHomePairingPayload:
        """
        Start smart home pairing via POST /api/smart_home/pairing.
        """
        logger.info("smart_home_pairing_start")
        data = self._request("POST", "/api/smart_home/pairing")
        return types.SmartHomePairingPayload.model_validate(data)

    def smart_home_pairing_stop(self) -> types.SuccessResponse:
        """
        Stop smart home pairing via DELETE /api/smart_home/pairing.
        """
        logger.info("smart_home_pairing_stop")
        data = self._request("DELETE", "/api/smart_home/pairing")
        return types.SuccessResponse.model_validate(data)

    def smart_home_switch(self) -> types.SmartHomeSwitchState:
        """
        Fetch smart home switch state via GET /api/smart_home/switch.
        """
        logger.info("smart_home_switch")
        data = self._request("GET", "/api/smart_home/switch")
        return types.SmartHomeSwitchState.model_validate(data)

    def smart_home_switch_set(
        self,
        state: bool,
        *,
        startup: Literal["off", "on", "toggle", "last"] | None = None,
    ) -> types.SuccessResponse:
        """
        Set smart home switch state via POST /api/smart_home/switch.
        """
        logger.info("smart_home_switch_set state=%s startup=%s", state, startup)
        payload = types.SmartHomeSwitchState(
            state=state,
            startup=startup,
        ).model_dump(exclude_none=True)
        data = self._request(
            "POST",
            "/api/smart_home/switch",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)


class AsyncSmartHomeMixin(AsyncClientBase):
    """
    Async smart home pairing and switch helpers.
    """

    async def smart_home_pairing(self) -> types.SmartHomePairingInfo:
        """
        Fetch smart home pairing status via GET /api/smart_home/pairing.
        """
        logger.info("async smart_home_pairing")
        data = await self._request("GET", "/api/smart_home/pairing")
        return types.SmartHomePairingInfo.model_validate(data)

    async def smart_home_pairing_start(self) -> types.SmartHomePairingPayload:
        """
        Start smart home pairing via POST /api/smart_home/pairing.
        """
        logger.info("async smart_home_pairing_start")
        data = await self._request("POST", "/api/smart_home/pairing")
        return types.SmartHomePairingPayload.model_validate(data)

    async def smart_home_pairing_stop(self) -> types.SuccessResponse:
        """
        Stop smart home pairing via DELETE /api/smart_home/pairing.
        """
        logger.info("async smart_home_pairing_stop")
        data = await self._request("DELETE", "/api/smart_home/pairing")
        return types.SuccessResponse.model_validate(data)

    async def smart_home_switch(self) -> types.SmartHomeSwitchState:
        """
        Fetch smart home switch state via GET /api/smart_home/switch.
        """
        logger.info("async smart_home_switch")
        data = await self._request("GET", "/api/smart_home/switch")
        return types.SmartHomeSwitchState.model_validate(data)

    async def smart_home_switch_set(
        self,
        state: bool,
        *,
        startup: Literal["off", "on", "toggle", "last"] | None = None,
    ) -> types.SuccessResponse:
        """
        Set smart home switch state via POST /api/smart_home/switch.
        """
        logger.info("async smart_home_switch_set state=%s startup=%s", state, startup)
        payload = types.SmartHomeSwitchState(
            state=state,
            startup=startup,
        ).model_dump(exclude_none=True)
        data = await self._request(
            "POST",
            "/api/smart_home/switch",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)
