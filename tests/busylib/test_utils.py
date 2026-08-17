from __future__ import annotations

import pytest

from busylib import types
from busylib._utils import normalize_rgba_color


@pytest.mark.parametrize("alpha", range(256))
def test_every_alpha_value_survives_normalization(alpha: int) -> None:
    """
    All 256 alpha values round-trip.

    15 of them used to be lost: pydantic's short hex form collapses byte pairs
    whose nibbles repeat, so "#FF000055" normalized to "#FF0000FF" and was
    drawn solid. Spot-checking a couple of values would have missed it, hence
    the exhaustive sweep.
    """
    assert normalize_rgba_color(f"#FF0000{alpha:02X}") == f"#FF0000{alpha:02X}"


def test_the_reported_cases() -> None:
    """
    The exact values from the bug report, including full transparency.
    """
    assert normalize_rgba_color("#FF000055") == "#FF000055"
    assert normalize_rgba_color("#00000000") == "#00000000"
    # Its neighbour was always fine, which is what made the bug look random.
    assert normalize_rgba_color("#FF000054") == "#FF000054"


def test_colors_without_an_alpha_channel_become_opaque() -> None:
    """
    An input carrying no alpha is completed with FF rather than left short.
    """
    assert normalize_rgba_color("#FF0000") == "#FF0000FF"
    assert normalize_rgba_color("red") == "#FF0000FF"
    assert normalize_rgba_color("rgb(1, 2, 3)") == "#010203FF"


def test_none_passes_through() -> None:
    """
    An absent colour stays absent instead of becoming a default.
    """
    assert normalize_rgba_color(None) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ((255, 0, 0), "#FF0000FF"),
        ((255, 0, 0, 85), "#FF000055"),
        ([0, 0, 0, 0], "#00000000"),
        # Floats in 0-1 are read as normalized channels.
        ((1.0, 0.0, 0.0, 0.5), "#FF000080"),
        # Out-of-range channels clamp rather than wrap.
        ((300, -20, 0, 999), "#FF0000FF"),
    ],
)
def test_tuples_and_lists(value: object, expected: str) -> None:
    """
    Sequence inputs cover both 0-255 integers and 0-1 floats.
    """
    assert normalize_rgba_color(value) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [(1, 2), (1, 2, 3, 4, 5)])
def test_sequences_of_the_wrong_length_are_rejected(value: object) -> None:
    """
    Only RGB and RGBA are meaningful, so anything else is an error.
    """
    with pytest.raises(ValueError, match="3 \\(RGB\\) or 4 \\(RGBA\\)"):
        normalize_rgba_color(value)  # type: ignore[arg-type]


def test_unsupported_types_are_rejected() -> None:
    """
    A non-colour is refused instead of being coerced.
    """
    with pytest.raises(ValueError, match="string or RGB/RGBA tuple"):
        normalize_rgba_color(42)  # type: ignore[arg-type]


def test_alpha_survives_model_validation() -> None:
    """
    The payload the device receives keeps the requested transparency.

    Normalization runs inside validation, so the bug altered elements after
    they had been accepted - which is how it reached the wire.
    """
    elements = types.DisplayElements.model_validate(
        {
            "application_name": "demo",
            "elements": [
                {
                    "id": "bg",
                    "type": "rectangle",
                    "width": 72,
                    "height": 16,
                    "fill": "solid",
                    "fill_colors": ["#FF000055"],
                }
            ],
        }
    )

    assert elements.elements[0].fill_colors == ["#FF000055"]
