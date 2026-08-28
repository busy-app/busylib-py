"""
Run this client's requests over someone else's HTTP session.

A host application often already owns a connection pool and wants everything
it does to go through it - Home Assistant hands integrations a shared
`aiohttp` session, and opening a second pool beside it wastes connections and
sidesteps the host's own timeouts and tracing.

`httpx2` already has the seam for this: a transport is one method. So nothing
in the client changes, and the default stays `httpx2`'s own transport.

    from busylib import AsyncBusyBar
    from busylib.transports import AiohttpTransport

    bb = AsyncBusyBar("10.0.4.20", transport=AiohttpTransport(session))

Status streaming is not affected: it speaks WebSocket through `websockets`,
not through the HTTP transport, so it keeps its own connection either way.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import httpx2

if TYPE_CHECKING:  # pragma: no cover - import for type checkers only
    import aiohttp

AIOHTTP_MISSING = (
    "AiohttpTransport needs aiohttp, which is optional: install busylib[aiohttp]."
)

# aiohttp sets these itself from the body it is given; forwarding the values
# httpx2 computed would describe a body aiohttp is no longer sending.
_HEADERS_AIOHTTP_OWNS = frozenset({"content-length", "transfer-encoding", "host"})


def _aiohttp() -> Any:
    """
    Import aiohttp on demand and explain plainly when it is absent.
    """
    try:
        import aiohttp
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(AIOHTTP_MISSING) from exc
    return aiohttp


class AiohttpTransport(httpx2.AsyncBaseTransport):
    """
    An httpx2 transport backed by an aiohttp session you already have.

    The session is borrowed, never closed: the caller owns its lifetime, and
    closing it here would break every other user of it.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._aiohttp = _aiohttp()

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        """
        Perform one request on the borrowed session.

        Errors are translated into `httpx2` transport errors, because that is
        the family the client catches to retry and to report; letting an
        aiohttp exception through would escape that handling entirely.
        """
        body = b"".join([chunk async for chunk in request.stream])  # type: ignore[union-attr]
        headers = [
            (key, value)
            for key, value in request.headers.items()
            if key.lower() not in _HEADERS_AIOHTTP_OWNS
        ]

        try:
            async with self._session.request(
                request.method,
                str(request.url),
                headers=headers,
                data=body or None,
                timeout=self._timeout(request),
                allow_redirects=False,
            ) as response:
                content = await response.read()
                return httpx2.Response(
                    response.status,
                    headers=list(response.headers.items()),
                    content=content,
                    request=request,
                )
        except asyncio.TimeoutError as exc:
            raise httpx2.ReadTimeout(str(exc) or "timed out", request=request) from exc
        except self._aiohttp.ClientConnectorError as exc:
            raise httpx2.ConnectError(str(exc), request=request) from exc
        except self._aiohttp.ClientError as exc:
            raise httpx2.TransportError(str(exc), request=request) from exc

    def _timeout(self, request: httpx2.Request) -> Any:
        """
        Translate the per-request timeout httpx2 attached, if there is one.
        """
        timeout = request.extensions.get("timeout") or {}
        return self._aiohttp.ClientTimeout(
            connect=timeout.get("connect"),
            sock_read=timeout.get("read"),
            sock_connect=timeout.get("connect"),
        )

    async def aclose(self) -> None:
        """
        Do nothing: the session belongs to whoever passed it in.
        """
