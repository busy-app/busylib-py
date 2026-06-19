from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class TimeMixin(SyncClientBase):
    """
    Device time and timezone helpers.
    """

    def time_timezone_info(self) -> types.TimezoneInfo:
        """
        Fetch current device timezone via GET /api/time/timezone.
        """
        logger.info("time_timezone_info")
        data = self._request("GET", "/api/time/timezone")
        return types.TimezoneInfo.model_validate(data)

    def time_timezone_list(self) -> types.TimezoneListResponse:
        """
        Fetch supported device timezones via GET /api/time/tzlist.
        """
        logger.info("time_timezone_list")
        data = self._request("GET", "/api/time/tzlist")
        return types.TimezoneListResponse.model_validate(data)

    def time_timestamp(self, timestamp: str) -> types.SuccessResponse:
        """
        Set device time via POST /api/time/timestamp.
        """
        logger.info("time_timestamp")
        params = {"timestamp": timestamp}
        data = self._request("POST", "/api/time/timestamp", params=params)
        return types.SuccessResponse.model_validate(data)

    def time_timezone(self, timezone: str) -> types.SuccessResponse:
        """
        Set device timezone via POST /api/time/timezone.
        """
        logger.info("time_timezone")
        params = {"timezone": timezone}
        data = self._request("POST", "/api/time/timezone", params=params)
        return types.SuccessResponse.model_validate(data)


class AsyncTimeMixin(AsyncClientBase):
    """
    Async device time and timezone helpers.
    """

    async def time_timezone_info(self) -> types.TimezoneInfo:
        """
        Fetch current device timezone via GET /api/time/timezone.
        """
        logger.info("async time_timezone_info")
        data = await self._request("GET", "/api/time/timezone")
        return types.TimezoneInfo.model_validate(data)

    async def time_timezone_list(self) -> types.TimezoneListResponse:
        """
        Fetch supported device timezones via GET /api/time/tzlist.
        """
        logger.info("async time_timezone_list")
        data = await self._request("GET", "/api/time/tzlist")
        return types.TimezoneListResponse.model_validate(data)

    async def time_timestamp(self, timestamp: str) -> types.SuccessResponse:
        """
        Set device time via POST /api/time/timestamp.
        """
        logger.info("async time_timestamp")
        params = {"timestamp": timestamp}
        data = await self._request("POST", "/api/time/timestamp", params=params)
        return types.SuccessResponse.model_validate(data)

    async def time_timezone(self, timezone: str) -> types.SuccessResponse:
        """
        Set device timezone via POST /api/time/timezone.
        """
        logger.info("async time_timezone")
        params = {"timezone": timezone}
        data = await self._request("POST", "/api/time/timezone", params=params)
        return types.SuccessResponse.model_validate(data)
