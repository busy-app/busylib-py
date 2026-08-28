"""
The aiohttp transport, exercised against a real local HTTP server.

A mock transport cannot test a transport: the point of this class is what it
does with sockets, headers and exceptions, so these tests speak to an actual
server over a real connection.
"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest
from aiohttp import web

from busylib import AsyncBusyBar, exceptions, types
from busylib.transports import AiohttpTransport


@pytest.fixture
async def server():
    """
    A small stand-in for the bar's HTTP API, plus a record of what it saw.
    """
    seen: dict[str, object] = {}

    async def version(_request: web.Request) -> web.Response:
        return web.json_response({"api_semver": "25.0.0"})

    async def draw(request: web.Request) -> web.Response:
        seen["method"] = request.method
        seen["content_type"] = request.headers.get("Content-Type")
        seen["token"] = request.headers.get("X-API-Token")
        seen["body"] = await request.json()
        return web.json_response({"result": "OK"})

    async def screen(_request: web.Request) -> web.Response:
        import base64

        payload = base64.b64encode(bytes([3, 2, 1]) * (72 * 16))
        return web.Response(body=payload, content_type="image/bmp")

    async def failing(_request: web.Request) -> web.Response:
        return web.json_response({"error": "nope", "code": 400}, status=400)

    app = web.Application()
    app.router.add_get("/api/version", version)
    app.router.add_post("/api/display/draw", draw)
    app.router.add_get("/api/screen", screen)
    app.router.add_get("/api/name", failing)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]

    yield f"http://127.0.0.1:{port}", seen

    await runner.cleanup()


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as client_session:
        yield client_session


async def test_a_json_response_round_trips(server, session) -> None:
    """
    The simplest path: a GET parsed into a model.
    """
    addr, _ = server
    bar = AsyncBusyBar(addr, transport=AiohttpTransport(session))

    assert (await bar.version()).api_semver == "25.0.0"

    await bar.aclose()


async def test_the_request_arrives_intact(server, session) -> None:
    """
    Method, body, content type and the device token all survive the hop.

    The transport rewrites headers - aiohttp computes its own content-length
    from the body it is handed - so the ones that carry meaning have to be
    checked rather than assumed.
    """
    addr, seen = server
    bar = AsyncBusyBar(addr, token="1234", transport=AiohttpTransport(session))

    await bar.display_draw(
        types.DisplayElements(
            application_name="probe",
            elements=[
                types.TextElement(
                    id="t",
                    type="text",
                    x=0,
                    y=0,
                    text="HI",
                    font="small",
                    display=types.DisplayName.FRONT,
                )
            ],
        )
    )

    assert seen["method"] == "POST"
    assert seen["token"] == "1234"
    assert str(seen["content_type"]).startswith("application/json")
    assert seen["body"]["application_name"] == "probe"  # type: ignore[index]

    await bar.aclose()


async def test_binary_responses_survive(server, session) -> None:
    """
    A screen frame comes back byte for byte, not decoded as text.
    """
    addr, _ = server
    bar = AsyncBusyBar(addr, transport=AiohttpTransport(session))

    frame = await bar.frame(0)

    assert frame.pixel(0, 0) == (1, 2, 3)

    await bar.aclose()


async def test_an_error_status_still_raises_the_domain_error(server, session) -> None:
    """
    HTTP failures keep their meaning through the adapter.
    """
    addr, _ = server
    bar = AsyncBusyBar(addr, transport=AiohttpTransport(session))

    with pytest.raises(exceptions.BusyBarAPIError) as caught:
        await bar.name()

    assert caught.value.status_code == 400

    await bar.aclose()


async def test_connection_failures_become_transport_errors(session) -> None:
    """
    An unreachable address raises what the client retries on.

    The client only catches `httpx2.RequestError`; an aiohttp exception
    reaching it unchanged would escape the retry and the error mapping
    entirely, so the translation is the whole job.
    """
    bar = AsyncBusyBar(
        "http://127.0.0.1:1",
        transport=AiohttpTransport(session),
        max_retries=0,
        timeout=2.0,
    )

    with pytest.raises(exceptions.BusyBarRequestError):
        await bar.version()

    await bar.aclose()


async def test_the_session_is_borrowed_not_owned(server, session) -> None:
    """
    Closing the client leaves the caller's session usable.

    Home Assistant hands out one session for the whole process; closing it
    would break every other integration sharing it.
    """
    addr, _ = server
    bar = AsyncBusyBar(addr, transport=AiohttpTransport(session))
    await bar.version()

    await bar.aclose()

    assert not session.closed
    async with session.get(f"{addr}/api/version") as response:
        assert response.status == 200


def test_the_module_does_not_import_aiohttp_eagerly() -> None:
    """
    aiohttp is optional, so importing busylib must not require it.
    """
    import subprocess
    import sys

    code = "import sys, busylib; print('aiohttp' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "False", result.stdout


async def test_a_slow_server_times_out(session) -> None:
    """
    The client's timeout is honoured by the borrowed session.

    httpx2 attaches the per-request timeout as an extension; without
    translating it the request would hang on aiohttp's own defaults.
    """

    async def slow(_request: web.Request) -> web.Response:
        await asyncio.sleep(5)
        return web.json_response({"api_semver": "25.0.0"})

    app = web.Application()
    app.router.add_get("/api/version", slow)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]

    bar = AsyncBusyBar(
        f"http://127.0.0.1:{port}",
        transport=AiohttpTransport(session),
        max_retries=0,
        timeout=0.5,
    )
    try:
        with pytest.raises(exceptions.BusyBarRequestError):
            await bar.version()
    finally:
        await bar.aclose()
        await runner.cleanup()
