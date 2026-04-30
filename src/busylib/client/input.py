from __future__ import annotations

import json
import logging
from typing import AsyncIterator
from urllib.parse import urlparse, urlunparse

import websockets

from .. import exceptions, types
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


def _http_to_ws(addr: str) -> str:
    """
    Convert HTTP(S) base address to WS(S) base address.

    The helper mirrors screen streaming behavior and keeps protocol mapping
    in one place for input websocket connections.
    """
    parsed = urlparse(addr if "://" in addr else f"http://{addr}")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse(parsed._replace(scheme=scheme))


def _normalize_event_state(value: object) -> types.InputEventState:
    """
    Normalize various event state representations to InputEventState.

    Accepts common shorthand forms used by websocket payloads:
    1/true/"press"/"down" for press and 0/false/"release"/"up" for release.
    """
    if isinstance(value, bool):
        return types.InputEventState.PRESS if value else types.InputEventState.RELEASE
    if isinstance(value, int):
        if value == 1:
            return types.InputEventState.PRESS
        if value == 0:
            return types.InputEventState.RELEASE
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "press", "pressed", "down"}:
            return types.InputEventState.PRESS
        if lowered in {"0", "release", "released", "up"}:
            return types.InputEventState.RELEASE
    raise ValueError(f"Unsupported input event state: {value!r}")


def _extract_event_payload(payload: dict[str, object]) -> dict[str, object]:
    """
    Build a canonical InputEvent payload from JSON websocket message.

    Supports both explicit shape (`{\"key\":\"ok\",\"state\":\"press\"}`) and
    shorthand shape (`{\"ok\":1}`) used by input control websocket payloads.
    """
    if "key" in payload:
        key = payload.get("key")
        if not isinstance(key, str):
            raise ValueError("Input event key must be a string")
        state = _normalize_event_state(payload.get("state"))
        return {
            "key": key,
            "state": state.value,
            "timestamp_ms": payload.get("timestamp_ms"),
        }

    known_keys = {key.value for key in types.InputKey}
    for key_name in known_keys:
        if key_name in payload:
            state = _normalize_event_state(payload.get(key_name))
            return {
                "key": key_name,
                "state": state.value,
                "timestamp_ms": payload.get("timestamp_ms"),
            }

    raise ValueError("Input event payload does not contain known key fields")


class InputMixin(SyncClientBase):
    """
    Input key events.
    """

    def send_input_key(self, key: types.InputKey) -> types.SuccessResponse:
        """
        Send one input key press via POST /api/input.

        This method is intended for command-style key forwarding.
        """
        logger.info("send_input_key key=%s", key.value)
        data = self._request(
            "POST",
            "/api/input",
            params={"key": key.value},
        )
        return types.SuccessResponse.model_validate(data)

    def stream_input_events_ws(self) -> None:
        """
        Subscribe to physical input events from device buttons.

        This API is reserved for future firmware support. Current firmware
        exposes `/api/input` as a control channel and does not publish button
        events to websocket clients.
        """
        raise NotImplementedError(
            "Input events websocket is not implemented in current firmware."
        )

    def parse_input_event_message(self, message: bytes | str) -> types.InputEvent:
        """
        Parse websocket message into typed InputEvent model.

        This parser is prepared for future input-events endpoint and supports
        both explicit and shorthand JSON payloads.
        """
        try:
            text = message.decode("utf-8") if isinstance(message, bytes) else message
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("Input event message must be a JSON object")
            normalized = _extract_event_payload(payload)
            return types.InputEvent.model_validate(normalized)
        except Exception as exc:
            raise exceptions.BusyBarProtocolError(
                "Failed to parse input event message",
                method="GET",
                path="/api/input/events",
                response_excerpt=str(message)[:256],
            ) from exc


class AsyncInputMixin(AsyncClientBase):
    """
    Async input key events.
    """

    async def send_input_key(self, key: types.InputKey) -> types.SuccessResponse:
        """
        Send one input key press via POST /api/input.

        This method is intended for command-style key forwarding.
        """
        logger.info("async send_input_key key=%s", key.value)
        data = await self._request(
            "POST",
            "/api/input",
            params={"key": key.value},
        )
        return types.SuccessResponse.model_validate(data)

    async def stream_input_ws(self) -> AsyncIterator[bytes | str]:
        """
        Open control websocket to send input state to GET /api/input endpoint.

        This endpoint accepts JSON key state payloads and applies them on the
        device. It is not a stream of physical button events.
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

        ws_url = _http_to_ws(self.base_url).rstrip("/") + "/api/input"
        if token:
            ws_url += f"?x-api-token={token}"

        try:
            async with websockets.connect(
                ws_url,
                max_size=None,
                ping_interval=None,
            ) as ws:
                async for message in ws:
                    yield message
        except Exception as exc:
            raise exceptions.BusyBarWebSocketError(
                "WebSocket streaming failed",
                path="/api/input",
                original=exc,
            ) from exc

    async def stream_input_events_ws(self) -> AsyncIterator[bytes | str]:
        """
        Subscribe to physical input events from device buttons.

        This API is reserved for future firmware support. Current firmware
        exposes `/api/input` as a control channel and does not publish button
        events to websocket clients.
        """
        raise NotImplementedError(
            "Input events websocket is not implemented in current firmware."
        )
        if False:  # pragma: no cover
            yield ""

    def parse_input_event_message(self, message: bytes | str) -> types.InputEvent:
        """
        Parse websocket message into typed InputEvent model.

        Async and sync clients share the same event message parsing contract.
        """
        try:
            text = message.decode("utf-8") if isinstance(message, bytes) else message
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("Input event message must be a JSON object")
            normalized = _extract_event_payload(payload)
            return types.InputEvent.model_validate(normalized)
        except Exception as exc:
            raise exceptions.BusyBarProtocolError(
                "Failed to parse input event message",
                method="GET",
                path="/api/input/events",
                response_excerpt=str(message)[:256],
            ) from exc
