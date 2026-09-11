from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


def _as_key(key: types.InputKey) -> types.InputKey:
    """
    Check the key, and say something useful when it is not one.

    The signature is the enum on purpose: which keys the bar has is the
    interface's business, not something a caller should discover from the
    firmware by sending a wrong one. This only exists for the call that
    slipped past a type checker - a key read out of configuration, a
    dynamically typed caller - which used to fail inside the request with
    "'str' object has no attribute 'value'".
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

    def input(self, key: types.InputKey) -> types.SuccessResponse:
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

    async def input(self, key: types.InputKey) -> types.SuccessResponse:
        key = _as_key(key)
        logger.info("async input key=%s", key.value)
        data = await self._request(
            "POST",
            "/api/input",
            params={"key": key.value},
        )
        return types.SuccessResponse.model_validate(data)
