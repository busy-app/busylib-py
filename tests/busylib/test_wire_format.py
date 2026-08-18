"""
Payload shapes the device actually accepts.

Both cases here were found by running against real firmware and had passed
mock-based tests for months: a mock accepts any query string, so nothing
noticed that the device did not.
"""

from __future__ import annotations

import httpx
import pytest

from busylib import BusyBar, types


def _client(seen: dict[str, object]) -> BusyBar:
    def responder(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"result": "OK"})

    return BusyBar(addr="http://device.local", transport=httpx.MockTransport(responder))


@pytest.mark.parametrize(
    "given,expected",
    [(42, "42"), (42.0, "42"), (42.4, "42"), (42.5, "43"), (100, "100"), (0, "0")],
)
def test_volume_goes_on_the_wire_without_a_decimal_point(
    given: float, expected: str
) -> None:
    """
    The device answers 400 for `?volume=42.0` and 200 for `?volume=42`.

    The OpenAPI document says `number`, so the model was a float and every
    call from this client was rejected. Floats are still accepted from callers
    and rounded half up.
    """
    seen: dict[str, object] = {}

    _client(seen).audio_volume_set(given)

    assert seen["params"] == {"volume": expected}


def test_volume_model_holds_a_whole_number() -> None:
    """
    The rounding happens in the model, so any caller of it benefits.
    """
    assert types.AudioVolumeUpdate(volume=42.5).volume == 43
    assert isinstance(types.AudioVolumeUpdate(volume=42.0).volume, int)


def test_rename_sends_the_source_as_path() -> None:
    """
    The device names the source `path`; `old_path` is rejected with 400.

    The Python keyword stays `old_path` because it reads better beside
    `new_path`, but only the wire name matters to the bar.
    """
    seen: dict[str, object] = {}

    _client(seen).storage_rename(old_path="/ext/a.txt", new_path="/ext/b.txt")

    assert seen["path"] == "/api/storage/rename"
    assert seen["params"] == {"path": "/ext/a.txt", "new_path": "/ext/b.txt"}
