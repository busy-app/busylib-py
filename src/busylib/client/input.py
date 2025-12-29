from __future__ import annotations

import logging

from .base import AsyncClientBase, SyncClientBase
from .. import types

logger = logging.getLogger(__name__)


class InputMixin(SyncClientBase):
    """
    Input key events.
    """

    def send_input_key(self, key: types.InputKey) -> types.SuccessResponse:
        logger.info("send_input_key key=%s", key.value)
        data = self._request(
            "POST",
            "/api/input",
            params={"key": key.value},
        )
        return types.SuccessResponse.model_validate(data)


class AsyncInputMixin(AsyncClientBase):
    """
    Async input key events.
    """

    async def send_input_key(self, key: types.InputKey) -> types.SuccessResponse:
        logger.info("async send_input_key key=%s", key.value)
        data = await self._request(
            "POST",
            "/api/input",
            params={"key": key.value},
        )
        return types.SuccessResponse.model_validate(data)
