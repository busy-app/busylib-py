"""
Input events survive the protobuf-to-dictionary conversion.

protobuf omits any field holding its default, and the first entry of an enum
is the default, so a press of OK - button 0, action 0 - used to arrive as an
empty `button_event`. The payloads below are the wire bytes from issue #77.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from busylib.client.state_stream import _decode_state
from busylib.state_stream_proto import state_pb2

# Captured from /api/status/ws while pressing and releasing the encoder.
PRESS = bytes.fromhex("12045a020a00")
RELEASE = bytes.fromhex("12065a040a0210 01".replace(" ", ""))


def _state(payload: bytes) -> Any:
    schema = cast(Any, state_pb2)
    message = schema.State()
    message.ParseFromString(payload)
    return message


def test_a_zero_valued_button_event_keeps_both_fields() -> None:
    """
    OK pressed is reported as OK pressed, not as an empty message.
    """
    decoded = _decode_state(_state(PRESS))

    assert decoded["updates"][0]["input"]["button_event"] == {
        "button": "OK",
        "action": "PRESS",
    }


def test_a_partially_defaulted_event_is_completed() -> None:
    """
    Release carries an action but not the button, which is still OK.
    """
    decoded = _decode_state(_state(RELEASE))

    assert decoded["updates"][0]["input"]["button_event"] == {
        "button": "OK",
        "action": "RELEASE",
    }


@pytest.mark.parametrize(
    "position,expected",
    [(0, "BUSY"), (1, "CUSTOM"), (2, "OFF"), (3, "APPS"), (4, "SETTINGS")],
)
def test_switch_positions_are_named_including_the_zero_one(
    position: int, expected: str
) -> None:
    """
    BUSY is position 0, so it hit the same problem as OK.
    """
    schema = cast(Any, state_pb2)
    message = schema.State()
    message.updates.add().input.switch_event.position = position

    decoded = _decode_state(message)

    assert decoded["updates"][0]["input"]["switch_event"] == {"position": expected}


def test_other_updates_are_not_padded_with_defaults() -> None:
    """
    Only the input subtree is completed.

    Filling defaults across the whole state would add zeroes for everything the
    device chose not to send, which is a far larger change than this needs.
    """
    schema = cast(Any, state_pb2)
    message = schema.State()
    message.updates.add().device_name.name = "bar"

    decoded = _decode_state(message)

    assert decoded["updates"][0]["device_name"] == {"name": "bar"}


def test_a_state_without_updates_is_untouched() -> None:
    """
    The normalization must not invent an updates list.
    """
    schema = cast(Any, state_pb2)
    message = schema.State(timestamp=7)

    decoded = _decode_state(message)

    assert decoded == {"timestamp": "7"}
