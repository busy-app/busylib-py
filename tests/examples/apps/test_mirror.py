"""
The picture of the bar's display, kept from the status stream.
"""

from __future__ import annotations

import base64

import pytest
from examples.apps.mirror import KEYS, Mirror
from examples.apps.view import draw

WIDTH, HEIGHT = 72, 16


def message(
    colour: tuple[int, int, int] = (255, 0, 0), *, screen: str = "FRONT"
) -> dict:
    """
    A status message carrying one frame, as the stream sends it: every pixel
    `colour`, in the order the device sends it, which is blue first.
    """
    data = bytes(colour) * (WIDTH * HEIGHT)
    return {
        "updates": [
            {"timer": {}},
            {"frame": {"screen": screen, "data": base64.b64encode(data).decode()}},
        ]
    }


def test_a_frame_on_the_stream_becomes_the_picture() -> None:
    mirror = Mirror()

    mirror.feed(message((255, 0, 0)))

    assert mirror.frame is not None
    assert (mirror.frame.width, mirror.frame.height) == (WIDTH, HEIGHT)
    assert mirror.frame.pixel(0, 0) == (0, 0, 255), "blue first on the wire"


def test_the_version_moves_only_when_the_picture_does() -> None:
    """
    The display is redrawn on a timer; a version that rose with every frame
    would redraw a picture that has not changed ten times a second.
    """
    mirror = Mirror()
    mirror.feed(message())
    first = mirror.version

    mirror.feed(message())
    assert mirror.version == first

    mirror.feed(message((0, 0, 255)))
    assert mirror.version == first + 1


@pytest.mark.parametrize(
    "garbage",
    [
        {},
        {"updates": "no"},
        {"updates": [None, 3, {"frame": "x"}, {"frame": {}}]},
        {"updates": [{"frame": {"screen": "FRONT", "data": "!!!not base64!!!"}}]},
        {"updates": [{"frame": {"screen": "FRONT", "data": "AAAA"}}]},
    ],
)
def test_a_frame_that_cannot_be_read_is_skipped_not_fatal(garbage: dict) -> None:
    mirror = Mirror()
    mirror.feed(message())

    mirror.feed(garbage)

    assert mirror.frame is not None, "the last good picture stays"


def test_the_back_display_is_not_the_picture() -> None:
    mirror = Mirror()

    mirror.feed(message(screen="BACK"))

    assert mirror.frame is None


def test_the_display_asked_for_outright_is_a_picture_too() -> None:
    mirror = Mirror()

    mirror.show_screen(bytes(WIDTH * HEIGHT * 3))
    assert mirror.frame is not None

    mirror.show_screen(b"short")
    assert mirror.frame is not None, "a wrong size is ignored"


def test_clearing_is_a_change_once() -> None:
    mirror = Mirror()
    mirror.feed(message())
    before = mirror.version

    mirror.clear()
    mirror.clear()

    assert mirror.frame is None
    assert mirror.version == before + 1


def test_every_name_on_the_remote_is_a_key_of_the_bar() -> None:
    assert sorted(KEYS) == sorted(
        ["back", "ok", "start", "left", "right", "busy", "custom", "off", "apps"]
        + ["settings"]
    )
    # Scrolling right is the bar's "up": the selection moves to the next item.
    assert KEYS["right"].name == "UP" and KEYS["left"].name == "DOWN"


def test_a_frame_is_drawn_two_rows_of_pixels_to_a_line() -> None:
    """
    The upper pixel is the character's colour and the lower its background,
    so the 72x16 panel is 72 characters wide and 8 lines tall, and a pixel
    keeps its shape.
    """
    mirror = Mirror()
    mirror.feed(message((255, 0, 0)))  # blue, on the wire
    assert mirror.frame is not None

    text = draw(mirror.frame)

    lines = text.plain.splitlines()
    assert (len(lines), {len(line) for line in lines}) == (8, {72})
    first = text.spans[0].style
    assert first.color.triplet == (0, 0, 255)  # type: ignore[union-attr]
    assert first.bgcolor.triplet == (0, 0, 255)  # type: ignore[union-attr]


def test_the_upper_pixel_is_the_colour_and_the_lower_the_background() -> None:
    mirror = Mirror()
    top = bytes((0, 0, 255)) * 72  # wire order: red
    bottom = bytes((255, 0, 0)) * 72  # wire order: blue
    data = (top + bottom) * 8
    mirror.feed(
        {
            "updates": [
                {
                    "frame": {
                        "screen": "FRONT",
                        "data": base64.b64encode(data).decode(),
                    }
                }
            ]
        }
    )
    assert mirror.frame is not None

    style = draw(mirror.frame).spans[0].style

    assert style.color.triplet == (255, 0, 0)  # type: ignore[union-attr]
    assert style.bgcolor.triplet == (0, 0, 255)  # type: ignore[union-attr]
