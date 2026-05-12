from __future__ import annotations

import logging
from typing import Any

from typing_extensions import Unpack

from .. import types
from .base import AsyncClientBase, RequestKwargs, SyncClientBase

logger = logging.getLogger(__name__)

AUDIO_PLAY_PATH = "/api/audio/play"


class AudioMixin(SyncClientBase):
    """
    Audio playback and volume control helpers.
    """

    def audio_play(
        self,
        *,
        path: str | None = None,
        stock_path: str | None = None,
        payload: types.AudioPlayRequest | dict[str, Any] | None = None,
        **request_kwargs: Unpack[RequestKwargs],
    ) -> types.SuccessResponse:
        """
        Play audio through POST /api/audio/play.

        The endpoint payload may reference either an uploaded asset path or a
        stock path. Explicit `path` and `stock_path` keyword arguments override
        the same keys provided in `payload`. Request context such as
        `application_name` and `session_id` is accepted through request kwargs;
        use `api_request` for fully custom bodies.
        """
        if payload is None:
            request_payload: dict[str, Any] = {}
        else:
            request_model = (
                payload
                if isinstance(payload, types.AudioPlayRequest)
                else types.AudioPlayRequest.model_validate(payload)
            )
            request_payload = request_model.model_dump(exclude_none=True)

        if path is not None:
            request_payload["path"] = path
            request_payload.pop("stock_path", None)
        if stock_path is not None:
            request_payload["stock_path"] = stock_path
            request_payload.pop("path", None)

        request_model = types.AudioPlayRequest.model_validate(request_payload)
        request_payload = request_model.model_dump(exclude_none=True)
        logger.info(
            "audio_play application_name=%s path=%s stock_path=%s",
            request_kwargs.get("application_name"),
            request_model.path,
            request_model.stock_path,
        )
        data = self._request(
            "POST",
            AUDIO_PLAY_PATH,
            json_payload=request_payload,
            **request_kwargs,
        )
        return types.SuccessResponse.model_validate(data)

    def audio_stop(self) -> types.SuccessResponse:
        """
        Stop audio through DELETE /api/audio/play.

        Uses API-like naming for callers that mirror firmware endpoints.
        """
        logger.info("audio_stop")
        data = self._request("DELETE", "/api/audio/play")
        return types.SuccessResponse.model_validate(data)

    def audio_volume(self) -> types.AudioVolumeInfo:
        logger.info("audio_volume")
        data = self._request("GET", "/api/audio/volume")
        return types.AudioVolumeInfo.model_validate(data)

    def audio_volume_set(self, volume: float) -> types.SuccessResponse:
        logger.info("audio_volume_set volume=%s", volume)
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

    async def audio_play(
        self,
        *,
        path: str | None = None,
        stock_path: str | None = None,
        payload: types.AudioPlayRequest | dict[str, Any] | None = None,
        **request_kwargs: Unpack[RequestKwargs],
    ) -> types.SuccessResponse:
        """
        Play audio through async POST /api/audio/play.

        The endpoint payload may reference either an uploaded asset path or a
        stock path. Explicit `path` and `stock_path` keyword arguments override
        the same keys provided in `payload`. Request context such as
        `application_name` and `session_id` is accepted through request kwargs;
        use `api_request` for fully custom bodies.
        """
        if payload is None:
            request_payload: dict[str, Any] = {}
        else:
            request_model = (
                payload
                if isinstance(payload, types.AudioPlayRequest)
                else types.AudioPlayRequest.model_validate(payload)
            )
            request_payload = request_model.model_dump(exclude_none=True)

        if path is not None:
            request_payload["path"] = path
            request_payload.pop("stock_path", None)
        if stock_path is not None:
            request_payload["stock_path"] = stock_path
            request_payload.pop("path", None)

        request_model = types.AudioPlayRequest.model_validate(request_payload)
        request_payload = request_model.model_dump(exclude_none=True)
        logger.info(
            "async audio_play application_name=%s path=%s stock_path=%s",
            request_kwargs.get("application_name"),
            request_model.path,
            request_model.stock_path,
        )
        data = await self._request(
            "POST",
            AUDIO_PLAY_PATH,
            json_payload=request_payload,
            **request_kwargs,
        )
        return types.SuccessResponse.model_validate(data)

    async def audio_stop(self) -> types.SuccessResponse:
        """
        Stop audio through async DELETE /api/audio/play.

        Uses API-like naming for callers that mirror firmware endpoints.
        """
        logger.info("async audio_stop")
        data = await self._request("DELETE", "/api/audio/play")
        return types.SuccessResponse.model_validate(data)

    async def audio_volume(self) -> types.AudioVolumeInfo:
        logger.info("async audio_volume")
        data = await self._request("GET", "/api/audio/volume")
        return types.AudioVolumeInfo.model_validate(data)

    async def audio_volume_set(self, volume: float) -> types.SuccessResponse:
        logger.info("async audio_volume_set volume=%s", volume)
        model = types.AudioVolumeUpdate(volume=volume)
        payload = model.model_dump()
        data = await self._request(
            "POST",
            "/api/audio/volume",
            params=payload,
        )
        return types.SuccessResponse.model_validate(data)
