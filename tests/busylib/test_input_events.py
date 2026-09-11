"""
Reading the bar's buttons, selector and wheel off the state stream.
"""

from __future__ import annotations

import pytest

from busylib import types
from busylib.client.input import _as_key
from busylib.features import input_events
from busylib.features.input_events import ButtonEvent, EncoderEvent, SelectorEvent


def _message(*updates: dict) -> dict:
    return {"timestamp": 1, "updates": list(updates)}


def test_a_press_and_a_release_are_both_reported() -> None:
    """
    Both halves are on the stream, so a consumer can tell a long press
    from a short one.
    """
    events = input_events(
        _message(
            {"input": {"button_event": {"button": "OK", "action": "PRESS"}}},
            {"input": {"button_event": {"button": "OK", "action": "RELEASE"}}},
        )
    )

    pressed, released = events
    assert pressed == ButtonEvent(button="ok", action="press")
    assert released == ButtonEvent(button="ok", action="release")
    # The narrowing is for the type checker as much as the reader: the
    # list holds the union of every input event.
    assert isinstance(pressed, ButtonEvent) and pressed.is_press
    assert isinstance(released, ButtonEvent) and not released.is_press


def test_the_firmwares_first_enum_values_survive_being_omitted() -> None:
    """
    proto3 omits an enum holding its first value, and OK and PRESS are
    both first - so an empty button event is a press of OK, not nothing.
    """
    events = input_events(_message({"input": {"button_event": {}}}))

    assert events == [ButtonEvent(button="ok", action="press")]


def test_the_selector_reports_where_it_was_moved_to() -> None:
    events = input_events(_message({"input": {"switch_event": {"position": "CUSTOM"}}}))

    assert events == [SelectorEvent(position="custom")]


def test_an_omitted_selector_position_is_the_first_one() -> None:
    events = input_events(_message({"input": {"switch_event": {}}}))

    assert events == [SelectorEvent(position="busy")]


def test_the_wheel_reports_how_far_it_turned() -> None:
    events = input_events(
        _message(
            {"input": {"encoder_event": {"delta": 3}}},
            {"input": {"encoder_event": {"delta": -1}}},
            {"input": {"encoder_event": {}}},
        )
    )

    assert events == [EncoderEvent(3), EncoderEvent(-1), EncoderEvent(0)]


def test_input_is_picked_out_of_everything_else_on_the_stream() -> None:
    """
    The stream is dominated by frames, and a message usually carries no
    input at all.
    """
    assert input_events(_message({"frame": {"data": "..."}}, {"timer": {}})) == []
    assert input_events({"updates": "not a list"}) == []
    assert input_events({}) == []


def test_an_event_this_version_does_not_know_is_skipped() -> None:
    """
    A newer firmware may put something else in an input update, and one
    unknown event must not hide the ones alongside it.
    """
    events = input_events(
        _message(
            {"input": {"something_new": {"whatever": 1}}},
            {"input": {"button_event": {"button": "BACK", "action": "PRESS"}}},
        )
    )

    assert events == [ButtonEvent(button="back", action="press")]


def test_a_key_that_slipped_past_the_type_checker_is_still_checked() -> None:
    """
    The signature is the enum, so this is only about the call that got
    past it: a key read out of configuration, or a dynamically typed
    caller. It used to fail inside the request with "'str' object has no
    attribute 'value'".
    """
    assert _as_key(types.InputKey.BACK) is types.InputKey.BACK
    assert _as_key("ok") is types.InputKey.OK  # type: ignore[arg-type]


def test_an_unknown_key_says_what_the_bar_has() -> None:
    with pytest.raises(ValueError, match="the bar has: apps, back, busy"):
        _as_key("middle")  # type: ignore[arg-type]
