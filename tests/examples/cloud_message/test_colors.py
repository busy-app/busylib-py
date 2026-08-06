from __future__ import annotations

import pytest

from examples.cloud_message.colors import ColorError, parse_color


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("red", (0xFF, 0x00, 0x00, 0xFF)),
        ("RED", (0xFF, 0x00, 0x00, 0xFF)),
        ("  white  ", (0xFF, 0xFF, 0xFF, 0xFF)),
        ("#FF0000", (0xFF, 0x00, 0x00, 0xFF)),
        ("ff0000", (0xFF, 0x00, 0x00, 0xFF)),
        ("#FF000055", (0xFF, 0x00, 0x00, 0x55)),
        ("red@40", (0xFF, 0x00, 0x00, 0x66)),
        ("red@0", (0xFF, 0x00, 0x00, 0x00)),
        ("red@100", (0xFF, 0x00, 0x00, 0xFF)),
        ("#FF0000@50", (0xFF, 0x00, 0x00, 0x80)),
        ("orange", (0xFF, 0x80, 0x00, 0xFF)),
    ],
)
def test_parse_color_accepted_forms(value: str, expected: tuple[int, ...]) -> None:
    """
    Names, hex values, and percentage alpha all resolve to RGBA channels.
    """
    assert parse_color(value) == expected


def test_parse_color_applies_default_alpha_to_bare_color() -> None:
    """
    A color without its own alpha picks up the caller's default.
    """
    assert parse_color("red", default_alpha=0x55) == (0xFF, 0x00, 0x00, 0x55)


def test_parse_color_explicit_alpha_beats_default() -> None:
    """
    An alpha carried by the value itself wins over the caller's default, so a
    translucent overlay default cannot silently override an explicit choice.
    """
    assert parse_color("#FF0000FF", default_alpha=0x55) == (0xFF, 0x00, 0x00, 0xFF)
    assert parse_color("red@100", default_alpha=0x55) == (0xFF, 0x00, 0x00, 0xFF)


@pytest.mark.parametrize(
    "value",
    ["puce", "#GGGGGG", "#FFF", "", "red@120", "red@-1", "red@abc"],
)
def test_parse_color_rejects_invalid_values(value: str) -> None:
    """
    Unknown names, malformed hex, and out-of-range alpha raise ColorError.
    """
    with pytest.raises(ColorError):
        parse_color(value)
