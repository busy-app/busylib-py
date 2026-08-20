"""
How the connection mode is chosen.

Cloud mode used to be selected by *omitting* `addr`, so a cloud host could
not be named: pointing at a non-production environment looked like an
ordinary `addr=...` and quietly became a device connection, with the device's
token header and the device's `/api` paths. `is_cloud` states it instead.
"""

from __future__ import annotations

import httpx
import pytest

from busylib import AsyncBusyBar, BusyBar


def _client(**kwargs) -> BusyBar:
    return BusyBar(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200)), **kwargs
    )


@pytest.mark.parametrize(
    "kwargs,mode",
    [
        ({}, "local"),
        ({"token": "s"}, "cloud"),
        ({"addr": "10.0.4.20"}, "network"),
        ({"addr": "192.168.1.5", "token": "1234"}, "network"),
    ],
)
def test_inference_is_unchanged(kwargs: dict, mode: str) -> None:
    """
    Without the flag, every existing call resolves exactly as before.
    """
    client = _client(**kwargs)

    assert client.connection_type == mode

    client.close()


def test_a_cloud_host_can_be_named() -> None:
    """
    An explicit cloud address gets cloud paths and the bearer header.

    This is the case that used to be impossible: the address was taken as a
    device, so requests went to /api with the wrong credential and failed
    without saying why.
    """
    client = _client(addr="https://api.dev.busy.app", token="s", is_cloud=True)

    assert client.connection_type == "cloud"
    assert client.base_url == "https://api.dev.busy.app"
    assert client.prepare_request("GET", "/api/version").path == "/busybar/version"
    assert client.client.headers["authorization"] == "Bearer s"

    client.close()


def test_cloud_without_an_address_uses_the_configured_host() -> None:
    """
    `is_cloud=True` alone still means the default cloud host.
    """
    client = _client(token="s", is_cloud=True)

    assert client.base_url == "https://api.busy.app"

    client.close()


def test_a_token_can_be_kept_local() -> None:
    """
    `is_cloud=False` keeps a tokened client on the device.

    That is a bar with an access key, which takes the device header rather
    than a bearer token.
    """
    client = _client(token="1234", is_cloud=False)

    assert client.connection_type == "local"
    assert client.prepare_request("GET", "/api/version").path == "/api/version"
    assert client.client.headers["x-api-token"] == "1234"

    client.close()


@pytest.mark.asyncio
async def test_the_async_client_agrees() -> None:
    """
    Both clients resolve the mode the same way.
    """
    client = AsyncBusyBar(
        addr="https://api.stage.busy.app",
        token="s",
        is_cloud=True,
        transport=httpx.MockTransport(lambda _r: httpx.Response(200)),
    )

    assert client.connection_type == "cloud"
    assert client.base_url == "https://api.stage.busy.app"
    assert client.prepare_request("GET", "/api/status").path == "/busybar/status"

    await client.aclose()


@pytest.mark.parametrize("cls", [BusyBar, AsyncBusyBar])
def test_the_parameters_are_visible_on_the_public_client(cls: type) -> None:
    """
    The public clients spell their arguments out.

    They forwarded `*args, **kwargs`, so editors and the generated reference
    showed no parameters at all - including `addr` and `token`.
    """
    import inspect

    params = inspect.signature(cls).parameters

    for name in ("addr", "token", "is_cloud", "timeout", "transport"):
        assert name in params, f"{cls.__name__} hides {name}"
