from __future__ import annotations

import os
import logging
from typing import Any, AsyncIterator
from urllib.parse import urlparse, urlunparse
import json

import websockets

from .base import AsyncClientBase, SyncClientBase
from .. import display, types

logger = logging.getLogger(__name__)


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


def _decode_frame_bytes(data: bytes, display_index: int, *, from_ws: bool) -> bytes | None:
    spec = display.get_display_spec(display_index)
    width, height = spec.width, spec.height
    expected = width * height * 3
    nibble_expected = (width * height) // 2
    gray_expected = width * height

    if from_ws:
        blk_size = 2 if display_index == 1 else 3
        decoded = _rle_decode(data, blk_size)
        if decoded:
            data = decoded

    if len(data) == expected:
        return data

    if len(data) == nibble_expected:
        unpacked = _back_b4_to_b8(data)
        return b"".join(bytes((v * 17, v * 17, v * 17)) for v in unpacked)

    if len(data) == gray_expected:
        factor = 17 if display_index == 1 else 1
        return b"".join(bytes((v * factor, v * factor, v * factor)) for v in data)

    return None


def _ws_auth_headers(base_url: str, client_headers: dict[str, str] | None) -> dict[str, str]:
    return dict(client_headers) if client_headers else {}


class DisplayMixin(SyncClientBase):
    """
    Display drawing, brightness control, and screen capture helpers.
    """

    def draw_on_display(
        self,
        display_data: types.DisplayElements | dict[str, Any],
    ) -> types.SuccessResponse:
        logger.info(
            "draw_on_display app_id=%s",
            display_data.app_id if isinstance(display_data, types.DisplayElements) else display_data.get("app_id"),
        )
        model = (
            display_data
            if isinstance(display_data, types.DisplayElements)
            else types.DisplayElements.model_validate(display_data)
        )
        payload = model.model_dump(exclude_none=True)
        self._warn_if_out_of_bounds(payload["elements"])
        data = self._request(
            "POST",
            "/api/display/draw",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

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

    def clear_display(self) -> types.SuccessResponse:
        logger.info("clear_display")
        data = self._request("DELETE", "/api/display/draw")
        return types.SuccessResponse.model_validate(data)

    def get_display_brightness(self) -> types.DisplayBrightnessInfo:
        logger.info("get_display_brightness")
        data = self._request("GET", "/api/display/brightness")
        return types.DisplayBrightnessInfo.model_validate(data)

    def set_display_brightness(
        self,
        front: types.BrightnessValue | None = None,
        back: types.BrightnessValue | None = None,
    ) -> types.SuccessResponse:
        logger.info("set_display_brightness front=%s back=%s", front, back)
        model = types.DisplayBrightnessUpdate(front=front, back=back)
        payload = model.model_dump(exclude_none=True)
        data = self._request(
            "POST",
            "/api/display/brightness",
            params=payload or None,
        )
        return types.SuccessResponse.model_validate(data)

    def get_screen_frame(self, display: int) -> bytes:
        """
        Fetch a single display frame via GET /api/screen.

        The handler returns raw framebuffer bytes without compression. Client
        must pass `display` query param: 0 for front (RGB, 24 bpp, 72x16 =>
        3456 bytes) or 1 for back (L4 grayscale, 160x80 => 6400 bytes). Server
        replies 200 with `image/bmp` content type or 400 when the display index
        is invalid. Response is decoded to RGB bytes when possible.
        """
        logger.info("get_screen_frame display=%s", display)
        data = self._request(
            "GET",
            "/api/screen",
            params={"display": display},
            expect_bytes=True,
        )  # type: ignore[return-value]
        decoded = _decode_frame_bytes(data, display, from_ws=False)
        return decoded if decoded is not None else data

    def stream_screen_ws(self, display: int) -> None:
        """
        WebSocket streaming via GET /api/screen/ws.

        Server upgrades HTTP to WebSocket; client must send `{"display": 0|1}`
        JSON to select front/back. Server streams binary frames compressed with
        RLE: front encodes runs of 3-byte BGR pixels (source 72x16x24bpp =>
        3456 bytes before compression); back encodes runs of 1-byte L4 values
        (source 160x80 L4 => 6400 bytes before compression). Frame sizes vary.
        Up to 4 clients supported; otherwise 400 Exceed max clients count.
        Heartbeat: server pings, client must respond with pong. Not implemented
        in this sync client; use busylib.screen CLI or a WebSocket client.
        """
        raise NotImplementedError("WebSocket streaming is not implemented in this client.")


class AsyncDisplayMixin(AsyncClientBase):
    """
    Async display drawing, brightness control, and screen capture helpers.
    """

    async def draw_on_display(
        self,
        display_data: types.DisplayElements | dict[str, Any],
    ) -> types.SuccessResponse:
        logger.info(
            "async draw_on_display app_id=%s",
            display_data.app_id if isinstance(display_data, types.DisplayElements) else display_data.get("app_id"),
        )
        model = (
            display_data
            if isinstance(display_data, types.DisplayElements)
            else types.DisplayElements.model_validate(display_data)
        )
        payload = model.model_dump(exclude_none=True)
        self._warn_if_out_of_bounds(payload["elements"])
        data = await self._request(
            "POST",
            "/api/display/draw",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

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

    async def clear_display(self) -> types.SuccessResponse:
        logger.info("async clear_display")
        data = await self._request("DELETE", "/api/display/draw")
        return types.SuccessResponse.model_validate(data)

    async def get_display_brightness(self) -> types.DisplayBrightnessInfo:
        logger.info("async get_display_brightness")
        data = await self._request("GET", "/api/display/brightness")
        return types.DisplayBrightnessInfo.model_validate(data)

    async def set_display_brightness(
        self,
        front: types.BrightnessValue | None = None,
        back: types.BrightnessValue | None = None,
    ) -> types.SuccessResponse:
        logger.info("async set_display_brightness front=%s back=%s", front, back)
        model = types.DisplayBrightnessUpdate(front=front, back=back)
        payload = model.model_dump(exclude_none=True)
        data = await self._request(
            "POST",
            "/api/display/brightness",
            params=payload or None,
        )
        return types.SuccessResponse.model_validate(data)

    async def get_screen_frame(self, display: int) -> bytes:
        """
        Fetch a single display frame via GET /api/screen.

        The handler returns raw framebuffer bytes without compression. Client
        must pass `display` query param: 0 for front (RGB, 24 bpp, 72x16 =>
        3456 bytes) or 1 for back (L4 grayscale, 160x80 => 6400 bytes). Server
        replies 200 with `image/bmp` content type or 400 when the display index
        is invalid. Response is decoded to RGB bytes when possible.
        """
        logger.info("async get_screen_frame display=%s", display)
        data = await self._request(
            "GET",
            "/api/screen",
            params={"display": display},
            expect_bytes=True,
        )  # type: ignore[return-value]
        decoded = _decode_frame_bytes(data, display, from_ws=False)
        return decoded if decoded is not None else data

    async def stream_screen_ws(self, display: int) -> AsyncIterator[bytes]:
        """
        WebSocket streaming via GET /api/screen/ws.

        Server upgrades HTTP to WebSocket; client must send `{"display": 0|1}`
        JSON to select front/back. Server streams binary frames compressed with
        RLE: front encodes runs of 3-byte BGR pixels (source 72x16x24bpp =>
        3456 bytes before compression); back encodes runs of 1-byte L4 values
        (source 160x80 L4 => 6400 bytes before compression). Frame sizes vary.
        Up to 4 clients supported; otherwise 400 Exceed max clients count.
        Heartbeat: server pings, client must respond with pong. This client
        disables automatic pings and relies on websockets' built-in pong
        replies to server pings. Token for WS upgrade is passed in query
        param `x-api-token`, per server implementation.
        """
        headers = dict(self.client.headers) if self.client.headers else {}
        # Token for WS upgrade is carried in query per server implementation.
        token = self.client.headers.get("Authorization")
        if token and token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1]
        else:
            token = headers.get("x-api-token") or headers.get("X-API-Token")

        ws_url = _http_to_ws(self.base_url).rstrip("/") + "/api/screen/ws"
        if token:
            ws_url += f"?x-api-token={token}"

        async with websockets.connect(
            ws_url,
            additional_headers=headers or None,
            max_size=None,
            ping_interval=None,
        ) as ws:
            await ws.send(json.dumps({"display": display}))
            async for message in ws:
                if isinstance(message, bytes):
                    decoded = _decode_frame_bytes(message, display, from_ws=True)
                    yield decoded if decoded is not None else message
                    continue

                # websockets delivers pings as a call to ws.ping() on the protocol,
                # so text frames are unexpected here; just log and continue.
                logger.debug("Ignoring text WS message len=%s", len(message))
