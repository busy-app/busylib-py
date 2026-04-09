from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, cast
from urllib.parse import quote, urlparse, urlunparse

import websockets
from typing_extensions import Unpack

from .. import display, exceptions, types
from .base import AsyncClientBase, RequestKwargs, SyncClientBase

logger = logging.getLogger(__name__)
_WS_MAX_SIZE = 4 * 1024 * 1024
_WS_PING_INTERVAL_SECONDS = 20
_WS_PING_TIMEOUT_SECONDS = 20

DISPLAY_DRAW_PATH = "/api/display/draw"
_EMOJI_AND_SYMBOLS_PATTERN = re.compile(
    "[\U0001f300-\U0001faff\u2600-\u27bf\u200d\ufe0f]",
)
_CONTROL_PATTERN = re.compile(r"[\x00-\x1F\x7F]")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_SANITIZE_LOG_TEXT_LIMIT = 80


def _http_to_ws(addr: str) -> str:
    parsed = urlparse(addr if "://" in addr else f"http://{addr}")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse(parsed._replace(scheme=scheme))


def _rle_decode(data: bytes, blk_size: int) -> bytes | None:
    out = bytearray()
    i = 0
    total = len(data)
    while i < total:
        ctrl = data[i]
        i += 1
        if ctrl & 0x80:
            count = ctrl & 0x7F
            need = count * blk_size
            if i + need > total:
                return None
            out.extend(data[i : i + need])
            i += need
        else:
            count = ctrl
            if i + blk_size > total:
                return None
            block = data[i : i + blk_size]
            i += blk_size
            out.extend(block * count)
    return bytes(out)


def _back_b4_to_b8(data: bytes) -> bytes:
    out = bytearray(len(data) * 2)
    idx = 0
    for byte in data:
        px1 = byte & 0x0F
        px2 = (byte >> 4) & 0x0F
        out[idx] = px1
        out[idx + 1] = px2
        idx += 2
    return bytes(out)


def _decode_frame_bytes(data: bytes, display_id: int, *, from_ws: bool) -> bytes | None:
    spec = display.get_display_spec(display_id)
    width, height = spec.width, spec.height
    expected = width * height * 3
    nibble_expected = (width * height) // 2
    gray_expected = width * height

    if from_ws:
        blk_size = 2 if display_id == 1 else 3
        decoded = _rle_decode(data, blk_size)
        if decoded:
            data = decoded

    if len(data) == expected:
        return data

    if len(data) == nibble_expected:
        unpacked = _back_b4_to_b8(data)
        return b"".join(bytes((v * 17, v * 17, v * 17)) for v in unpacked)

    if len(data) == gray_expected:
        factor = 17 if display_id == 1 else 1
        return b"".join(bytes((v * factor, v * factor, v * factor)) for v in data)

    return None


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

        The handler returns raw framebuffer bytes without compression. Client
        must pass `display` query param: 0 for front (RGB, 24 bpp, 72x16 =>
        3456 bytes) or 1 for back (L4 grayscale, 160x80 => 6400 bytes).
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
        decoded = _decode_frame_bytes(data, target.index, from_ws=False)
        return decoded if decoded is not None else data

    def screen_ws(self, display_id: int) -> None:
        """
        WebSocket streaming via GET /api/screen/ws.

        Server upgrades HTTP to WebSocket. This sync client intentionally does
        not implement streaming; use the async client for WebSocket frames.
        """
        raise NotImplementedError(
            "WebSocket streaming is implemented only for async client."
        )


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

        The handler returns raw framebuffer bytes without compression. Client
        must pass `display` query param: 0 for front (RGB, 24 bpp, 72x16 =>
        3456 bytes) or 1 for back (L4 grayscale, 160x80 => 6400 bytes).
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
        decoded = _decode_frame_bytes(data, target.index, from_ws=False)
        return decoded if decoded is not None else data

    async def screen_ws(self, display_id: int) -> AsyncIterator[bytes | str]:
        """
        Stream display frames via GET /api/screen/ws.

        Yields bytes for image frames and strings for server messages.
        """
        headers = self.client.headers
        token = headers.get("Authorization") if headers else None
        if token and token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1]
        else:
            token = (
                None
                if headers is None
                else (headers.get("x-api-token") or headers.get("X-API-Token"))
            )

        target = display.get_display_spec(display_id)
        ws_url = _http_to_ws(self.base_url).rstrip("/") + "/api/screen/ws"
        if token:
            ws_url += f"?x-api-token={quote(token, safe='')}"

        try:
            async with websockets.connect(
                ws_url,
                max_size=_WS_MAX_SIZE,
                ping_interval=_WS_PING_INTERVAL_SECONDS,
                ping_timeout=_WS_PING_TIMEOUT_SECONDS,
            ) as ws:
                await ws.send(json.dumps({"display": target.index}))
                async for message in ws:
                    if isinstance(message, bytes):
                        decoded = _decode_frame_bytes(
                            message,
                            target.index,
                            from_ws=True,
                        )
                        yield decoded if decoded is not None else message
                    else:
                        yield message
        except Exception as exc:
            raise exceptions.BusyBarWebSocketError(
                "WebSocket streaming failed",
                path="/api/screen/ws",
                original=exc,
            ) from exc
