from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class InputMixin(SyncClientBase):
    """
    Input key events.
    """

    def input(self, key: types.InputKey) -> types.SuccessResponse:
        logger.info("input key=%s", key.value)
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

    async def input(self, key: types.InputKey) -> types.SuccessResponse:
        logger.info("async input key=%s", key.value)
        data = await self._request(
            "POST",
            "/api/input",
            params={"key": key.value},
        )
        return types.SuccessResponse.model_validate(data)
