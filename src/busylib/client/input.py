from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


def _as_key(key: types.InputKey | str) -> types.InputKey:
    """
    Accept a key by name as well as by enum.

    A caller reading a key out of configuration - an automation, a CLI
    argument - has a string, and passing it used to fail inside the
    request with "'str' object has no attribute 'value'", which says
    nothing about what was wrong or what would be right.
    """
    try:
        return types.InputKey(key)
    except ValueError as exc:
        known = ", ".join(sorted(member.value for member in types.InputKey))
        raise ValueError(f"unknown input key {key!r}; the bar has: {known}") from exc


class InputMixin(SyncClientBase):
    """
    Input key events.
    """

    def input(self, key: types.InputKey | str) -> types.SuccessResponse:
        key = _as_key(key)
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

    async def input(self, key: types.InputKey | str) -> types.SuccessResponse:
        key = _as_key(key)
        logger.info("async input key=%s", key.value)
        data = await self._request(
            "POST",
            "/api/input",
            params={"key": key.value},
        )
        return types.SuccessResponse.model_validate(data)
