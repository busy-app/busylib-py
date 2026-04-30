from __future__ import annotations

import logging
from typing import Any

from .. import exceptions, types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class AudioMixin(SyncClientBase):
    """
    Audio playback and volume control helpers.
    """

    def play_audio(self, application_name: str, path: str) -> types.SuccessResponse:
        logger.info(
            "play_audio application_name=%s path=%s",
            application_name,
            path,
        )
        data = self._request(
            "POST",
            "/api/audio/play",
            params={"application_name": application_name, "path": path},
        )
        try:
            data = self._request(
                "POST",
                "/api/audio/play",
                json_payload=request_payload,
            )
            return types.SuccessResponse.model_validate(data)
        except exceptions.BusyBarAPIError as exc:
            if request_model.stock_path or exc.status_code != 400:
                raise
            data = self._request(
                "POST",
                "/api/audio/play",
                params={
                    "application_name": request_model.application_name,
                    "path": request_model.path,
                },
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

    async def play_audio(self, application_name: str, path: str) -> types.SuccessResponse:
        logger.info(
            "async play_audio application_name=%s path=%s",
            application_name,
            path,
        )
        data = await self._request(
            "POST",
            "/api/audio/play",
            params={"application_name": application_name, "path": path},
        )
        try:
            data = await self._request(
                "POST",
                "/api/audio/play",
                json_payload=request_payload,
            )
            return types.SuccessResponse.model_validate(data)
        except exceptions.BusyBarAPIError as exc:
            if request_model.stock_path or exc.status_code != 400:
                raise
            data = await self._request(
                "POST",
                "/api/audio/play",
                params={
                    "application_name": request_model.application_name,
                    "path": request_model.path,
                },
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
