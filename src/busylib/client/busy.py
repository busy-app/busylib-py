from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class BusyMixin(SyncClientBase):
    """
    Busy snapshot and profile helpers.
    """

    def busy_snapshot(self) -> types.BusySnapshot:
        """
        Fetch busy snapshot via GET /api/busy/snapshot.
        """
        logger.info("busy_snapshot")
        data = self._request("GET", "/api/busy/snapshot")
        return types.BusySnapshot.model_validate(data)

    def busy_snapshot_set(self, snapshot: types.BusySnapshot) -> types.SuccessResponse:
        """
        Set busy snapshot via PUT /api/busy/snapshot.
        """
        logger.info("busy_snapshot_set")
        payload = snapshot.model_dump(mode="json")
        data = self._request(
            "PUT",
            "/api/busy/snapshot",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

    def busy_profile(self, slot: types.BusyProfileSlot) -> types.BusyProfile:
        """
        Fetch a busy profile slot via GET /api/busy/profiles/{slot}.
        """
        logger.info("busy_profile slot=%s", slot)
        data = self._request("GET", f"/api/busy/profiles/{slot}")
        return types.BusyProfile.model_validate(data)

    def busy_profile_set(
        self,
        slot: types.BusyProfileSlot,
        profile: types.BusyProfile | dict[str, object],
    ) -> types.SuccessResponse:
        """
        Set a busy profile slot via PUT /api/busy/profiles/{slot}.
        """
        logger.info("busy_profile_set slot=%s", slot)
        model = (
            profile
            if isinstance(profile, types.BusyProfile)
            else types.BusyProfile.model_validate(profile)
        )
        data = self._request(
            "PUT",
            f"/api/busy/profiles/{slot}",
            json_payload=model.model_dump(mode="json"),
        )
        return types.SuccessResponse.model_validate(data)


class AsyncBusyMixin(AsyncClientBase):
    """
    Async busy snapshot and profile helpers.
    """

    async def busy_snapshot(self) -> types.BusySnapshot:
        """
        Fetch busy snapshot via GET /api/busy/snapshot.
        """
        logger.info("async busy_snapshot")
        data = await self._request("GET", "/api/busy/snapshot")
        return types.BusySnapshot.model_validate(data)

    async def busy_snapshot_set(
        self, snapshot: types.BusySnapshot
    ) -> types.SuccessResponse:
        """
        Set busy snapshot via PUT /api/busy/snapshot.
        """
        logger.info("async busy_snapshot_set")
        payload = snapshot.model_dump(mode="json")
        data = await self._request(
            "PUT",
            "/api/busy/snapshot",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

    async def busy_profile(self, slot: types.BusyProfileSlot) -> types.BusyProfile:
        """
        Fetch a busy profile slot via GET /api/busy/profiles/{slot}.
        """
        logger.info("async busy_profile slot=%s", slot)
        data = await self._request("GET", f"/api/busy/profiles/{slot}")
        return types.BusyProfile.model_validate(data)

    async def busy_profile_set(
        self,
        slot: types.BusyProfileSlot,
        profile: types.BusyProfile | dict[str, object],
    ) -> types.SuccessResponse:
        """
        Set a busy profile slot via PUT /api/busy/profiles/{slot}.
        """
        logger.info("async busy_profile_set slot=%s", slot)
        model = (
            profile
            if isinstance(profile, types.BusyProfile)
            else types.BusyProfile.model_validate(profile)
        )
        data = await self._request(
            "PUT",
            f"/api/busy/profiles/{slot}",
            json_payload=model.model_dump(mode="json"),
        )
        return types.SuccessResponse.model_validate(data)
