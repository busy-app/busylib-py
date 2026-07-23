from __future__ import annotations

import base64
import binascii
import logging
import re
from typing import Any, cast

from typing_extensions import Unpack

from .. import display, types
from .base import AsyncClientBase, RequestKwargs, SyncClientBase

logger = logging.getLogger(__name__)

DISPLAY_DRAW_PATH = "/api/display/draw"
_EMOJI_AND_SYMBOLS_PATTERN = re.compile(
    "[\U0001f300-\U0001faff\u2600-\u27bf\u200d\ufe0f]",
)
_CONTROL_PATTERN = re.compile(r"[\x00-\x1F\x7F]")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_SANITIZE_LOG_TEXT_LIMIT = 80


def _decode_frame_bytes(data: bytes, display_id: int) -> bytes | None:
    """
    Decode the `/api/screen` HTTP response into RGB888 bytes.

    The endpoint's `Content-Type: image/bmp` header is misleading: the body
    is base64-encoded (via mongoose's `mg_print_base64`), uncompressed
    framebuffer bytes with no real BMP header, RGB888 for the front display
    and L4-packed (2 pixels/byte) for the back display. Returns None if the
    payload cannot be decoded or its size doesn't match the display.
    """
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None

    pixel_format = "L4" if display_id == 1 else "RGB888"
    try:
        decoded = display.decode_frame_data("PLAIN", pixel_format, raw)
    except ValueError:
        return None

    spec = display.get_display_spec(display_id)
    if len(decoded) != spec.width * spec.height * 3:
        return None
    return decoded


def _sanitize_text_value(value: str) -> str:
    """
    Sanitize display text for firmware-safe rendering.
    """
    without_emoji = _EMOJI_AND_SYMBOLS_PATTERN.sub("", value)
    without_controls = _CONTROL_PATTERN.sub("", without_emoji)
    return _WHITESPACE_PATTERN.sub(" ", without_controls).strip()


def _truncate_log_text(value: str) -> str:
    """
    Shorten sanitized text samples for compact warning logs.
    """
    if len(value) <= _SANITIZE_LOG_TEXT_LIMIT:
        return value
    return f"{value[:_SANITIZE_LOG_TEXT_LIMIT]}..."


def _sanitize_display_payload_text(payload: dict[str, Any]) -> None:
    """
    Sanitize text elements in-place and log each changed element.
    """
    for element in payload.get("elements", []):
        if not isinstance(element, dict):
            continue
        if element.get("type") != "text":
            continue
        text = element.get("text")
        if isinstance(text, str):
            sanitized = _sanitize_text_value(text)
            if sanitized != text:
                logger.warning(
                    "Sanitized display text element_id=%s display=%s text_before=%r text_after=%r",
                    element.get("id", "?"),
                    element.get("display", types.DisplayName.FRONT.value),
                    _truncate_log_text(text),
                    _truncate_log_text(sanitized),
                )
            element["text"] = sanitized


class DisplayMixin(SyncClientBase):
    """
    Display drawing, brightness control, and screen capture helpers.
    """

    def display_draw(
        self,
        display_data: types.DisplayElements | dict[str, Any],
        *,
        clear_before_draw: bool = False,
        sanitize_text: bool = False,
        **request_kwargs: Unpack[RequestKwargs],
    ) -> types.SuccessResponse:
        logger.info(
            "display_draw application_name=%s clear_before_draw=%s",
            display_data.application_name
            if isinstance(display_data, types.DisplayElements)
            else display_data.get("application_name"),
            clear_before_draw,
        )
        model = (
            display_data
            if isinstance(display_data, types.DisplayElements)
            else types.DisplayElements.model_validate(display_data)
        )
        override_name = request_kwargs.get("application_name")
        if override_name and override_name != model.application_name:
            logger.warning(
                "display_draw application_name override payload=%s request=%s",
                model.application_name,
                override_name,
            )
        if clear_before_draw:
            clear_request_kwargs = cast(RequestKwargs, dict(request_kwargs))
            clear_request_kwargs.pop("application_name", None)
            self.display_clear(**clear_request_kwargs)
        payload = model.model_dump(exclude_none=True)
        if sanitize_text:
            _sanitize_display_payload_text(payload)
        self._warn_if_out_of_bounds(payload["elements"])
        data = self._request(
            "POST",
            DISPLAY_DRAW_PATH,
            json_payload=payload,
            **request_kwargs,
        )
        return types.SuccessResponse.model_validate(data)

    def display(
        self,
        display_data: types.DisplayElements | dict[str, Any],
        *,
        clear_before_draw: bool = False,
        sanitize_text: bool = False,
        audio_payload: types.AudioPlayRequest | dict[str, Any] | None = None,
        **request_kwargs: Unpack[RequestKwargs],
    ) -> types.SuccessResponse:
        """
        Render display content and optionally play audio after draw.

        Operations are sequential, not atomic: clear may succeed before draw
        fails, and audio failure may occur after display content is visible.
        Exceptions include the failed endpoint path for diagnostics.
        """
        model = (
            display_data
            if isinstance(display_data, types.DisplayElements)
            else types.DisplayElements.model_validate(display_data)
        )
        response = self.display_draw(
            model,
            clear_before_draw=clear_before_draw,
            sanitize_text=sanitize_text,
            **request_kwargs,
        )
        if audio_payload:
            audio_play = getattr(self, "audio_play", None)
            if audio_play is None:
                raise TypeError("display audio_payload requires AudioMixin.audio_play")
            audio_play(
                payload=audio_payload,
                **request_kwargs,
            )
        return response

    def _warn_if_out_of_bounds(self, elements: list[dict[str, Any]]) -> None:
        for element in elements:
            display_name = element.get("display", types.DisplayName.FRONT.value)
            spec = display.get_display_spec(display_name)
            x = element.get("x")
            y = element.get("y")
            width = element.get("width")
            if x is not None and x >= spec.width:
                logger.warning(
                    "Element %s x=%s exceeds %s width=%s",
                    element.get("id", "?"),
                    x,
                    spec.name.value,
                    spec.width,
                )
            if y is not None and y >= spec.height:
                logger.warning(
                    "Element %s y=%s exceeds %s height=%s",
                    element.get("id", "?"),
                    y,
                    spec.name.value,
                    spec.height,
                )
            if width is not None and x is not None and (x + width) > spec.width:
                logger.warning(
                    "Element %s x+width=%s exceeds %s width=%s",
                    element.get("id", "?"),
                    x + width,
                    spec.name.value,
                    spec.width,
                )

    def display_clear(
        self,
        **request_kwargs: Unpack[RequestKwargs],
    ) -> types.SuccessResponse:
        """
        Clear display content through DELETE /api/display/draw.

        Uses API-like naming for callers that mirror firmware endpoints.
        """
        logger.info(
            "display_clear application_name=%s",
            request_kwargs.get("application_name"),
        )
        data = self._request(
            "DELETE",
            DISPLAY_DRAW_PATH,
            **request_kwargs,
        )
        return types.SuccessResponse.model_validate(data)

    def display_brightness(self) -> types.DisplayBrightnessInfo:
        logger.info("display_brightness")
        data = self._request("GET", "/api/display/brightness")
        return types.DisplayBrightnessInfo.model_validate(data)

    def display_brightness_set(
        self,
        value: types.BrightnessValue,
    ) -> types.SuccessResponse:
        logger.info("display_brightness_set value=%s", value)
        model = types.DisplayBrightnessUpdate(value=value)
        payload = model.model_dump(exclude_none=True)
        data = self._request(
            "POST",
            "/api/display/brightness",
            params=payload or None,
        )
        return types.SuccessResponse.model_validate(data)

    def screen(self, display_id: int) -> bytes:
        """
        Fetch a single display frame via GET /api/screen.

        The response body is base64-encoded, uncompressed framebuffer bytes
        (the `Content-Type: image/bmp` header is misleading, there is no
        real BMP header). Client must pass `display` query param: 0 for
        front (RGB888, 72x16 => 3456 bytes decoded) or 1 for back
        (L4-packed, 160x80 => 6400 bytes decoded).
        """
        logger.info("screen display=%s", display_id)
        target = display.get_display_spec(display_id)
        raw = self._request(
            "GET",
            "/api/screen",
            params={"display": target.index},
            expect_bytes=True,
        )
        if not isinstance(raw, (bytes, bytearray)):
            raise TypeError("Expected bytes response for screen frame")
        data = bytes(raw)
        decoded = _decode_frame_bytes(data, target.index)
        return decoded if decoded is not None else data


class AsyncDisplayMixin(AsyncClientBase):
    """
    Async display drawing, brightness control, and screen capture helpers.
    """

    async def display_draw(
        self,
        display_data: types.DisplayElements | dict[str, Any],
        *,
        clear_before_draw: bool = False,
        sanitize_text: bool = False,
        **request_kwargs: Unpack[RequestKwargs],
    ) -> types.SuccessResponse:
        logger.info(
            "async display_draw application_name=%s clear_before_draw=%s",
            display_data.application_name
            if isinstance(display_data, types.DisplayElements)
            else display_data.get("application_name"),
            clear_before_draw,
        )
        model = (
            display_data
            if isinstance(display_data, types.DisplayElements)
            else types.DisplayElements.model_validate(display_data)
        )
        override_name = request_kwargs.get("application_name")
        if override_name and override_name != model.application_name:
            logger.warning(
                "async display_draw application_name override payload=%s request=%s",
                model.application_name,
                override_name,
            )
        if clear_before_draw:
            clear_request_kwargs = cast(RequestKwargs, dict(request_kwargs))
            clear_request_kwargs.pop("application_name", None)
            await self.display_clear(**clear_request_kwargs)
        payload = model.model_dump(exclude_none=True)
        if sanitize_text:
            _sanitize_display_payload_text(payload)
        self._warn_if_out_of_bounds(payload["elements"])
        data = await self._request(
            "POST",
            DISPLAY_DRAW_PATH,
            json_payload=payload,
            **request_kwargs,
        )
        return types.SuccessResponse.model_validate(data)

    async def display(
        self,
        display_data: types.DisplayElements | dict[str, Any],
        *,
        clear_before_draw: bool = False,
        sanitize_text: bool = False,
        audio_payload: types.AudioPlayRequest | dict[str, Any] | None = None,
        **request_kwargs: Unpack[RequestKwargs],
    ) -> types.SuccessResponse:
        """
        Render display content and optionally play audio after draw.

        Operations are sequential, not atomic: clear may succeed before draw
        fails, and audio failure may occur after display content is visible.
        Exceptions include the failed endpoint path for diagnostics.
        """
        model = (
            display_data
            if isinstance(display_data, types.DisplayElements)
            else types.DisplayElements.model_validate(display_data)
        )
        response = await self.display_draw(
            model,
            clear_before_draw=clear_before_draw,
            sanitize_text=sanitize_text,
            **request_kwargs,
        )
        if audio_payload:
            audio_play = getattr(self, "audio_play", None)
            if audio_play is None:
                raise TypeError(
                    "display audio_payload requires AsyncAudioMixin.audio_play"
                )
            await audio_play(
                payload=audio_payload,
                **request_kwargs,
            )
        return response

    def _warn_if_out_of_bounds(self, elements: list[dict[str, Any]]) -> None:
        for element in elements:
            display_name = element.get("display", types.DisplayName.FRONT.value)
            spec = display.get_display_spec(display_name)
            x = element.get("x")
            y = element.get("y")
            width = element.get("width")
            if x is not None and x >= spec.width:
                logger.warning(
                    "Element %s x=%s exceeds %s width=%s",
                    element.get("id", "?"),
                    x,
                    spec.name.value,
                    spec.width,
                )
            if y is not None and y >= spec.height:
                logger.warning(
                    "Element %s y=%s exceeds %s height=%s",
                    element.get("id", "?"),
                    y,
                    spec.name.value,
                    spec.height,
                )
            if width is not None and x is not None and (x + width) > spec.width:
                logger.warning(
                    "Element %s x+width=%s exceeds %s width=%s",
                    element.get("id", "?"),
                    x + width,
                    spec.name.value,
                    spec.width,
                )

    async def display_clear(
        self,
        **request_kwargs: Unpack[RequestKwargs],
    ) -> types.SuccessResponse:
        """
        Clear display content through async DELETE /api/display/draw.

        Uses API-like naming for callers that mirror firmware endpoints.
        """
        logger.info(
            "async display_clear application_name=%s",
            request_kwargs.get("application_name"),
        )
        data = await self._request(
            "DELETE",
            DISPLAY_DRAW_PATH,
            **request_kwargs,
        )
        return types.SuccessResponse.model_validate(data)

    async def display_brightness(self) -> types.DisplayBrightnessInfo:
        logger.info("async display_brightness")
        data = await self._request("GET", "/api/display/brightness")
        return types.DisplayBrightnessInfo.model_validate(data)

    async def display_brightness_set(
        self,
        value: types.BrightnessValue,
    ) -> types.SuccessResponse:
        logger.info("async display_brightness_set value=%s", value)
        model = types.DisplayBrightnessUpdate(value=value)
        payload = model.model_dump(exclude_none=True)
        data = await self._request(
            "POST",
            "/api/display/brightness",
            params=payload or None,
        )
        return types.SuccessResponse.model_validate(data)

    async def screen(self, display_id: int) -> bytes:
        """
        Fetch a single display frame via GET /api/screen.

        The response body is base64-encoded, uncompressed framebuffer bytes
        (the `Content-Type: image/bmp` header is misleading, there is no
        real BMP header). Client must pass `display` query param: 0 for
        front (RGB888, 72x16 => 3456 bytes decoded) or 1 for back
        (L4-packed, 160x80 => 6400 bytes decoded).
        """
        logger.info("async screen display=%s", display_id)
        target = display.get_display_spec(display_id)
        raw = await self._request(
            "GET",
            "/api/screen",
            params={"display": target.index},
            expect_bytes=True,
        )
        if not isinstance(raw, (bytes, bytearray)):
            raise TypeError("Expected bytes response for screen frame")
        data = bytes(raw)
        decoded = _decode_frame_bytes(data, target.index)
        return decoded if decoded is not None else data
