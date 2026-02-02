from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class BusyMixin(SyncClientBase):
    """
    Busy snapshot helpers.
    """

    def get_busy_snapshot(self) -> types.BusySnapshot:
        """
        Fetch busy snapshot via GET /api/busy/snapshot.
        """
        logger.info("get_busy_snapshot")
        data = self._request("GET", "/api/busy/snapshot")
        return types.BusySnapshot.model_validate(data)

    def set_busy_snapshot(self, snapshot: types.BusySnapshot) -> types.SuccessResponse:
        """
        Set busy snapshot via PUT /api/busy/snapshot.
        """
        logger.info("set_busy_snapshot")
        payload = snapshot.model_dump(mode="json")
        data = self._request(
            "PUT",
            "/api/busy/snapshot",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)


class AsyncBusyMixin(AsyncClientBase):
    """
    Async busy snapshot helpers.
    """

    async def get_busy_snapshot(self) -> types.BusySnapshot:
        """
        Fetch busy snapshot via GET /api/busy/snapshot.
        """
        logger.info("async get_busy_snapshot")
        data = await self._request("GET", "/api/busy/snapshot")
        return types.BusySnapshot.model_validate(data)

    async def set_busy_snapshot(
        self, snapshot: types.BusySnapshot
    ) -> types.SuccessResponse:
        """
        Set busy snapshot via PUT /api/busy/snapshot.
        """
        logger.info("async set_busy_snapshot")
        payload = snapshot.model_dump(mode="json")
        data = await self._request(
            "PUT",
            "/api/busy/snapshot",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)
