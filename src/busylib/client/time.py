from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class TimeMixin(SyncClientBase):
    """
    Device time helpers.
    """

    def set_time_timestamp(self, timestamp: str) -> types.SuccessResponse:
        """
        Set device time via POST /api/time/timestamp.
        """
        logger.info("set_time_timestamp")
        params = {"timestamp": timestamp}
        data = self._request("POST", "/api/time/timestamp", params=params)
        return types.SuccessResponse.model_validate(data)

    def set_time_timezone(self, timezone: str) -> types.SuccessResponse:
        """
        Set device timezone via POST /api/time/timezone.
        """
        logger.info("set_time_timezone")
        params = {"timezone": timezone}
        data = self._request("POST", "/api/time/timezone", params=params)
        return types.SuccessResponse.model_validate(data)


class AsyncTimeMixin(AsyncClientBase):
    """
    Async device time helpers.
    """

    async def set_time_timestamp(self, timestamp: str) -> types.SuccessResponse:
        """
        Set device time via POST /api/time/timestamp.
        """
        logger.info("async set_time_timestamp")
        params = {"timestamp": timestamp}
        data = await self._request("POST", "/api/time/timestamp", params=params)
        return types.SuccessResponse.model_validate(data)

    async def set_time_timezone(self, timezone: str) -> types.SuccessResponse:
        """
        Set device timezone via POST /api/time/timezone.
        """
        logger.info("async set_time_timezone")
        params = {"timezone": timezone}
        data = await self._request("POST", "/api/time/timezone", params=params)
        return types.SuccessResponse.model_validate(data)
