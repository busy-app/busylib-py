from __future__ import annotations

import logging

from .. import types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class AudioMixin(SyncClientBase):
    """
    Audio playback and volume control helpers.
    """

    def play_audio(self, app_id: str, path: str) -> types.SuccessResponse:
        logger.info("play_audio app_id=%s path=%s", app_id, path)
        data = self._request(
            "POST",
            "/api/audio/play",
            params={"app_id": app_id, "path": path},
        )
        return types.SuccessResponse.model_validate(data)

    def stop_audio(self) -> types.SuccessResponse:
        logger.info("stop_audio")
        data = self._request("DELETE", "/api/audio/play")
        return types.SuccessResponse.model_validate(data)

    def stop_sound(self) -> types.SuccessResponse:
        """
        Alias for stop_audio.

        Provided for callers that prefer "sound" naming.
        """
        return self.stop_audio()

    def get_audio_volume(self) -> types.AudioVolumeInfo:
        logger.info("get_audio_volume")
        data = self._request("GET", "/api/audio/volume")
        return types.AudioVolumeInfo.model_validate(data)

    def set_audio_volume(self, volume: float) -> types.SuccessResponse:
        logger.info("set_audio_volume volume=%s", volume)
        model = types.AudioVolumeUpdate(volume=volume)
        payload = model.model_dump()
        data = self._request(
            "POST",
            "/api/audio/volume",
            params=payload,
        )
        return types.SuccessResponse.model_validate(data)


class AsyncAudioMixin(AsyncClientBase):
    """
    Async audio playback and volume control helpers.
    """

    async def play_audio(self, app_id: str, path: str) -> types.SuccessResponse:
        logger.info("async play_audio app_id=%s path=%s", app_id, path)
        data = await self._request(
            "POST",
            "/api/audio/play",
            params={"app_id": app_id, "path": path},
        )
        return types.SuccessResponse.model_validate(data)

    async def stop_audio(self) -> types.SuccessResponse:
        logger.info("async stop_audio")
        data = await self._request("DELETE", "/api/audio/play")
        return types.SuccessResponse.model_validate(data)

    async def stop_sound(self) -> types.SuccessResponse:
        """
        Alias for stop_audio.

        Provided for callers that prefer "sound" naming.
        """
        return await self.stop_audio()

    async def get_audio_volume(self) -> types.AudioVolumeInfo:
        logger.info("async get_audio_volume")
        data = await self._request("GET", "/api/audio/volume")
        return types.AudioVolumeInfo.model_validate(data)

    async def set_audio_volume(self, volume: float) -> types.SuccessResponse:
        logger.info("async set_audio_volume volume=%s", volume)
        model = types.AudioVolumeUpdate(volume=volume)
        payload = model.model_dump()
        data = await self._request(
            "POST",
            "/api/audio/volume",
            params=payload,
        )
        return types.SuccessResponse.model_validate(data)
