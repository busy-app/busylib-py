from __future__ import annotations

import httpx
import pytest

from busylib import AsyncBusyBar, BusyBar
from busylib.client.base import _cloud_path
from busylib.settings import Settings


@pytest.mark.parametrize(
    "device_path,expected",
    [
        ("/api/version", "/busybar/version"),
        ("/api/status", "/busybar/status"),
        ("/api/display/draw", "/busybar/display/draw"),
        ("/api/access/tokens/ab12", "/busybar/access/tokens/ab12"),
        ("/api", "/busybar"),
        # Not under /api: left alone rather than guessed at.
        ("/openapi.yaml", "/openapi.yaml"),
        ("/busybar/version", "/busybar/version"),
        # Only the prefix is replaced, never a later occurrence.
        ("/api/assets/api", "/busybar/assets/api"),
    ],
)
def test_cloud_paths_replace_the_prefix(device_path: str, expected: str) -> None:
    """
    Cloud endpoints live under /busybar, and the cloud serves no /api at all.

    Overriding only the base URL was not enough, which is why cloud mode
    answered 404 for every call.
    """
    assert _cloud_path(device_path) == expected


def test_cloud_client_requests_the_cloud_path() -> None:
    """
    A client in cloud mode rewrites the path it was given.
    """
    seen: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"api_semver": "25.0.0"})

    client = BusyBar(token="secret", transport=httpx.MockTransport(responder))
    client.version()

    assert seen == ["/busybar/version"]


def test_device_client_keeps_the_device_path() -> None:
    """
    Nothing changes for a client talking to a bar directly.
    """
    seen: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"api_semver": "25.0.0"})

    client = BusyBar(addr="10.0.4.20", transport=httpx.MockTransport(responder))
    client.version()

    assert seen == ["/api/version"]


@pytest.mark.asyncio
async def test_async_cloud_client_requests_the_cloud_path() -> None:
    """
    The async client rewrites the same way.
    """
    seen: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"api_semver": "25.0.0"})

    client = AsyncBusyBar(token="secret", transport=httpx.MockTransport(responder))
    await client.version()
    await client.aclose()

    assert seen == ["/busybar/version"]


def test_prefixed_environment_variables_are_honoured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Both BUSYLIB_-prefixed and bare names work.

    An explicit `validation_alias` bypasses `env_prefix`, so the documented
    prefixed names were silently ignored and only the bare ones took effect.
    """
    monkeypatch.setenv("BUSYLIB_CLOUD_URL", "https://prefixed.test")
    monkeypatch.delenv("CLOUD_URL", raising=False)
    assert Settings().cloud_base_url == "https://prefixed.test"

    monkeypatch.delenv("BUSYLIB_CLOUD_URL")
    monkeypatch.setenv("CLOUD_URL", "https://bare.test")
    assert Settings().cloud_base_url == "https://bare.test"


def test_the_cloud_default_points_at_a_host_that_exists() -> None:
    """
    The default was proxy.busy.app, renamed before launch and never resolvable.
    """
    monkeypatched = Settings()

    assert monkeypatched.cloud_base_url == "https://api.busy.app"
