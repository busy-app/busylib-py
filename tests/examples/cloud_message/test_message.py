from __future__ import annotations

import pytest

from busylib import types
from examples.cloud_message.message import (
    APPLICATION_NAME,
    DEFAULT_PRIORITY,
    Message,
    build_elements,
)


def test_build_elements_produces_validated_payload() -> None:
    """
    A plain message becomes a scrolling white text element for this app.
    """
    elements = build_elements(Message(text="Deploy running"))

    assert isinstance(elements, types.DisplayElements)
    assert elements.application_name == APPLICATION_NAME
    assert elements.priority == DEFAULT_PRIORITY

    payload = elements.model_dump(exclude_none=True)
    assert len(payload["elements"]) == 1
    text = payload["elements"][0]
    assert text["type"] == "text"
    assert text["color"] == "#FFFFFFFF"
    assert text["scroll_rate"] == 600


def test_build_elements_background_is_translucent_and_drawn_last() -> None:
    """
    The background rectangle must be translucent and come after the text.

    A filled rectangle is composited over text regardless of element order, so
    an opaque fill would hide the message entirely.
    """
    elements = build_elements(Message(text="Deploy running", background="red"))
    payload = elements.model_dump(exclude_none=True)

    assert [element["type"] for element in payload["elements"]] == [
        "text",
        "rectangle",
    ]
    fill = payload["elements"][1]["fill_colors"][0]
    assert fill.startswith("#FF0000")
    assert fill != "#FF0000FF", "opaque background would hide the text"


def test_build_elements_omits_scroll_when_disabled() -> None:
    """
    Static text carries no scroll fields.
    """
    payload = build_elements(Message(text="Idle", scroll=False)).model_dump(
        exclude_none=True
    )
    assert "scroll_rate" not in payload["elements"][0]


def test_build_elements_sets_led_only_when_requested() -> None:
    """
    The status LED stays quiet unless a color is asked for.
    """
    without = build_elements(Message(text="Idle")).model_dump(exclude_none=True)
    assert "led_notification_color" not in without

    with_led = build_elements(Message(text="Idle", led="yellow")).model_dump(
        exclude_none=True
    )
    assert with_led["led_notification_color"] == "#FFFF00FF"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"text": "   "}, "must not be empty"),
        ({"text": "héllo"}, "printable ASCII"),
        ({"text": "ok", "priority": 0}, "between 1 and 100"),
        ({"text": "ok", "priority": 101}, "between 1 and 100"),
    ],
)
def test_message_rejects_invalid_input(kwargs: dict[str, object], match: str) -> None:
    """
    Validation happens before any device call.
    """
    with pytest.raises(ValueError, match=match):
        Message(**kwargs)  # type: ignore[arg-type]
