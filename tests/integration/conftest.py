"""
A real bar, reached three ways.

The same client code runs over USB, over the LAN, and through the cloud, so
these tests are parameterized by transport rather than duplicated per
transport. Anything that only works on one of them says so explicitly.

Nothing here runs by default: `-m integration` selects it, and each transport
is skipped unless it is configured and answers. Configuration is by
environment, so a laptop with a bar plugged in needs no arguments at all:

    BUSYBAR_TEST_USB          device address over USB   (default 10.0.4.20)
    BUSYBAR_TEST_WIFI         device address on the LAN
    BUSYBAR_TEST_WIFI_TOKEN   access key, if the bar has one set
    BUSYBAR_TEST_CLOUD_TOKEN  bar-scope cloud token
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from busylib import AsyncBusyBar, BusyBar

# Everything this suite writes is namespaced, so a failed run leaves rubbish
# that is easy to find and impossible to confuse with a user's own data.
APP_NAME = "busylib-itest"
STORAGE_DIR = "/ext/busylib-itest"

DEFAULT_USB_ADDR = "10.0.4.20"
PROBE_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class Transport:
    """
    One way of reaching the bar, and what it can be expected to do.
    """

    name: str
    addr: str | None
    token: str | None
    is_cloud: bool

    def sync_client(self, **kwargs: object) -> BusyBar:
        return BusyBar(addr=self.addr, token=self.token, **kwargs)  # type: ignore[arg-type]

    def async_client(self, **kwargs: object) -> AsyncBusyBar:
        return AsyncBusyBar(addr=self.addr, token=self.token, **kwargs)  # type: ignore[arg-type]


def _configured_transports() -> list[Transport]:
    """
    Build the transport list from the environment, in cost order.
    """
    found: list[Transport] = []

    usb_addr = os.environ.get("BUSYBAR_TEST_USB", DEFAULT_USB_ADDR)
    if usb_addr:
        found.append(Transport("usb", usb_addr, None, is_cloud=False))

    wifi_addr = os.environ.get("BUSYBAR_TEST_WIFI")
    if wifi_addr:
        found.append(
            Transport(
                "wifi",
                wifi_addr,
                os.environ.get("BUSYBAR_TEST_WIFI_TOKEN"),
                is_cloud=False,
            )
        )

    cloud_token = os.environ.get("BUSYBAR_TEST_CLOUD_TOKEN")
    if cloud_token:
        found.append(Transport("cloud", None, cloud_token, is_cloud=True))

    return found


TRANSPORTS = _configured_transports()


def _reachable(transport: Transport) -> str | None:
    """
    Return None when the bar answers, or the reason it did not.

    Probing once per session keeps a disconnected cable from producing dozens
    of identical timeouts.
    """
    try:
        client = transport.sync_client(timeout=PROBE_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - configuration errors count as unreachable
        return f"client could not be built: {exc}"
    try:
        # `status` rather than `version`: the bar answers /api/version without
        # a key even in key mode, so probing with it would let a transport
        # with a missing or wrong token look usable and fail every test.
        client.status()
    except Exception as exc:  # noqa: BLE001 - any failure means "not usable here"
        return f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
    return None


_REACHABILITY: dict[str, str | None] = {}


@pytest.fixture(scope="session", params=TRANSPORTS, ids=lambda t: t.name)
def transport(request: pytest.FixtureRequest) -> Transport:
    """
    Yield each configured transport, skipping any that does not answer.
    """
    chosen: Transport = request.param
    if chosen.name not in _REACHABILITY:
        _REACHABILITY[chosen.name] = _reachable(chosen)
    reason = _REACHABILITY[chosen.name]
    if reason is not None:
        pytest.skip(f"{chosen.name} transport unavailable - {reason}")
    return chosen


@pytest.fixture
def bar(transport: Transport):
    """
    A sync client for the transport under test.
    """
    client = transport.sync_client()
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
async def abar(transport: Transport):
    """
    An async client for the transport under test.
    """
    client = transport.async_client()
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def local_only(transport: Transport) -> Transport:
    """
    Skip the test unless the bar is reached directly.

    Status streaming is a local endpoint by design; the cloud lists it and
    refuses the upgrade.
    """
    if transport.is_cloud:
        pytest.skip("endpoint is local only")
    return transport
