"""
Two log_dump contracts living side by side.

The parameter changed at OpenAPI 25.0.0 - `path`, a full destination, became
`filename`, a bare name - and the two cannot be translated into each other.
Rather than dropping the old one and telling those callers to pin an old
release, both are kept and the device's version decides which is valid.
"""

from __future__ import annotations

import httpx2
import pytest

from busylib import AsyncBusyBar, BusyBar

OLD = "24.3.0"
NEW = "27.6.0"


def _client(seen: dict[str, object], device_api_version: str | None = None) -> BusyBar:
    def responder(request: httpx2.Request) -> httpx2.Response:
        seen["params"] = dict(request.url.params)
        return httpx2.Response(200, json={"result": "OK"})

    return BusyBar(
        "http://device.local",
        transport=httpx2.MockTransport(responder),
        device_api_version=device_api_version,
    )


@pytest.mark.parametrize("device", [OLD, NEW, None])
def test_without_an_argument_the_request_is_the_same_everywhere(device) -> None:
    """
    Both firmwares write to their own default, so no version is needed.

    This is the common call, and it is why the split does not have to reach
    every caller.
    """
    seen: dict[str, object] = {}

    _client(seen, device).log_dump()

    assert seen["params"] == {}


def test_a_current_device_takes_a_filename() -> None:
    seen: dict[str, object] = {}

    _client(seen, NEW).log_dump("log")

    assert seen["params"] == {"filename": "log"}


def test_an_older_device_takes_a_path() -> None:
    seen: dict[str, object] = {}

    _client(seen, OLD).log_dump(path="/ext/dump.log")

    assert seen["params"] == {"path": "/ext/dump.log"}


@pytest.mark.parametrize(
    "device,kwargs,expected",
    [
        (OLD, {"filename": "log"}, "takes path="),
        (NEW, {"path": "/ext/dump.log"}, "takes filename="),
    ],
)
def test_the_wrong_contract_is_refused_before_the_request(
    device: str, kwargs: dict, expected: str
) -> None:
    """
    A known-mismatched argument fails here, not as a bare 400 from the bar.
    """
    seen: dict[str, object] = {}

    with pytest.raises(ValueError, match=expected):
        _client(seen, device).log_dump(**kwargs)

    assert "params" not in seen, "nothing should have been sent"


@pytest.mark.parametrize("kwargs", [{"filename": "log"}, {"path": "/ext/dump.log"}])
def test_an_unknown_device_is_taken_at_the_caller_s_word(kwargs: dict) -> None:
    """
    With no version known, the request goes out as asked.

    A client that has not called `version()` knows nothing about the bar, and
    refusing on a guess would be worse than letting the device answer.
    """
    seen: dict[str, object] = {}

    _client(seen, None).log_dump(**kwargs)

    assert seen["params"] == {k: v for k, v in kwargs.items()}


def test_both_arguments_together_are_rejected() -> None:
    """
    They name different contracts, so asking for both is a mistake.
    """
    with pytest.raises(ValueError, match="not both"):
        _client({}, NEW).log_dump("log", path="/ext/dump.log")


def test_the_version_can_be_learned_instead_of_supplied() -> None:
    """
    `version()` fills it in, so a caller need not know it up front.
    """

    def responder(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/version":
            return httpx2.Response(200, json={"api_semver": OLD})
        return httpx2.Response(200, json={"result": "OK"})

    client = BusyBar("http://device.local", transport=httpx2.MockTransport(responder))
    assert client.device_at_least("25.0.0") is None

    client.version()

    assert client.device_at_least("25.0.0") is False
    with pytest.raises(ValueError, match="takes path="):
        client.log_dump("log")


@pytest.mark.asyncio
async def test_the_async_client_dispatches_the_same_way() -> None:
    seen: dict[str, object] = {}

    def responder(request: httpx2.Request) -> httpx2.Response:
        seen["params"] = dict(request.url.params)
        return httpx2.Response(200, json={"result": "OK"})

    client = AsyncBusyBar(
        "http://device.local",
        transport=httpx2.MockTransport(responder),
        device_api_version=OLD,
    )
    await client.log_dump(path="/ext/dump.log")
    await client.aclose()

    assert seen["params"] == {"path": "/ext/dump.log"}
