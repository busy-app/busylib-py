from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, cast
from collections.abc import AsyncIterator
from urllib.parse import quote, urlparse, urlunparse

from google.protobuf.json_format import MessageToDict
import websockets
import websockets.exceptions

from .. import exceptions
from ..state_stream_proto import state_pb2
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)
_WS_MAX_SIZE = 4 * 1024 * 1024
_WS_PING_INTERVAL_SECONDS = 20
_WS_PING_TIMEOUT_SECONDS = 20


def _http_to_ws(addr: str) -> str:
    """
    Convert HTTP(S) base URL into a WebSocket base URL.

    The helper preserves host, port, and path while swapping the scheme to
    ws/wss.
    """
    parsed = urlparse(addr if "://" in addr else f"http://{addr}")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse(parsed._replace(scheme=scheme))


def _extract_token(headers: Mapping[str, str]) -> str | None:
    """
    Extract API token from configured HTTP headers.

    Local clients use `X-API-Token`. Cloud status streaming is currently not
    supported in this client.
    """
    return headers.get("x-api-token") or headers.get("X-API-Token")


class StateStreamMixin(SyncClientBase):
    """
    Sync API for status streaming endpoints.

    WebSocket status streaming is implemented in async mode only.
    """

    def stream_status_ws(self) -> None:
        """
        Stream device status updates via WebSocket /api/status/ws.

        Sync iteration is not supported because websocket lifecycle and frame
        handling are asynchronous in this client implementation.
        """
        raise NotImplementedError(
            "Status WebSocket streaming is implemented only for async client."
        )


class AsyncStateStreamMixin(AsyncClientBase):
    """
    Async helpers for `/api/status/ws` protobuf state streaming.

    The method opens WebSocket connection, sends `{"enable": true}` handshake,
    then yields decoded protobuf state dictionaries or raw text messages.
    Current firmware publishes frame updates for front display only on this
    channel.
    """

    async def stream_status_ws(
        self,
        *,
        enable: bool = True,
        decode_protobuf: bool = True,
    ) -> AsyncIterator[dict[str, Any] | bytes | str]:
        """
        Open `/api/status/ws` and yield status updates.

        When `decode_protobuf=True`, binary frames are decoded using
        `BSB_State.State` protobuf schema from `bsb-protobuf` and converted into
        dictionaries with original proto field names.
        """
        if self.is_cloud:
            raise NotImplementedError(
                "Cloud mode is not supported for /api/status/ws streaming."
            )

        headers = self.client.headers
        token = _extract_token(headers)

        ws_url = _http_to_ws(self.base_url).rstrip("/") + "/api/status/ws"
        if token:
            ws_url += f"?x-api-token={quote(token, safe='')}"

        try:
            async with websockets.connect(
                ws_url,
                max_size=_WS_MAX_SIZE,
                ping_interval=_WS_PING_INTERVAL_SECONDS,
                ping_timeout=_WS_PING_TIMEOUT_SECONDS,
            ) as ws:
                if enable:
                    await ws.send(json.dumps({"enable": True}))

                async for message in ws:
                    if isinstance(message, str):
                        yield message
                        continue

                    if not decode_protobuf:
                        yield message
                        continue

                    try:
                        state_schema = cast(Any, state_pb2)
                        state_message = state_schema.State()
                        state_message.ParseFromString(message)
                        yield MessageToDict(
                            state_message,
                            preserving_proto_field_name=True,
                        )
                    except Exception as exc:
                        raise exceptions.BusyBarProtocolError(
                            "Failed to decode /api/status/ws protobuf message",
                            method="GET",
                            path="/api/status/ws",
                            response_excerpt=str(exc),
                        ) from exc
        except exceptions.BusyBarProtocolError:
            raise
        except websockets.exceptions.InvalidStatus as exc:
            status_code = exc.response.status_code
            if status_code in (401, 403):
                raise exceptions.BusyBarWebSocketError(
                    "Status WebSocket streaming failed: authentication required "
                    f"(HTTP {status_code}). Pass a valid --token",
                    path="/api/status/ws",
                    original=exc,
                ) from exc
            raise exceptions.BusyBarWebSocketError(
                "Status WebSocket streaming failed",
                path="/api/status/ws",
                original=exc,
            ) from exc
        except Exception as exc:
            raise exceptions.BusyBarWebSocketError(
                "Status WebSocket streaming failed",
                path="/api/status/ws",
                original=exc,
            ) from exc
