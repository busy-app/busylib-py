from __future__ import annotations

import httpx
import pytest

from busylib import AsyncBusyBar, BusyBar, types


def _make_sync_client(responder) -> BusyBar:
    """
    Build a BusyBar client with a mock transport responder.
    """
    transport = httpx.MockTransport(responder)
    return BusyBar(addr="http://device.local", transport=transport)


def _make_async_client(responder) -> AsyncBusyBar:
    """
    Build an AsyncBusyBar client with a mock transport responder.
    """
    transport = httpx.MockTransport(responder)
    return AsyncBusyBar(addr="http://device.local", transport=transport)


def test_send_input_key_sync() -> None:
    """
    Ensure sync input key events send the correct key parameter.
    """
    seen: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "params": dict(request.url.params),
                "method": request.method,
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_sync_client(responder)
    resp = client.send_input_key(types.InputKey.OK)
    assert resp.result == "OK"
    assert seen == [{"path": "/api/input", "params": {"key": "ok"}, "method": "POST"}]


@pytest.mark.asyncio
async def test_send_input_key_async() -> None:
    """
    Ensure async input key events send the correct key parameter.
    """
    seen: list[dict[str, object]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "path": request.url.path,
                "params": dict(request.url.params),
                "method": request.method,
            }
        )
        return httpx.Response(200, json={"result": "OK"})

    client = _make_async_client(responder)
    resp = await client.send_input_key(types.InputKey.OK)
    assert resp.result == "OK"
    await client.aclose()
    assert seen == [{"path": "/api/input", "params": {"key": "ok"}, "method": "POST"}]
