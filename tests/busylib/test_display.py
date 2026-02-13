from __future__ import annotations

import pytest

from busylib import display, types


def test_get_display_spec_defaults_to_front_for_none() -> None:
    """
    Use the front display only for implicit default selection.

    This verifies that passing None keeps existing front-default behavior.
    """
    spec = display.get_display_spec(None)
    assert spec.name == types.DisplayName.FRONT
    assert spec.index == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (types.DisplayName.FRONT, types.DisplayName.FRONT),
        (types.DisplayName.BACK, types.DisplayName.BACK),
        (0, types.DisplayName.FRONT),
        (1, types.DisplayName.BACK),
        ("front", types.DisplayName.FRONT),
        ("back", types.DisplayName.BACK),
        ("  back  ", types.DisplayName.BACK),
    ],
)
def test_get_display_spec_accepts_explicit_valid_values(
    value: types.DisplayName | int | str,
    expected: types.DisplayName,
) -> None:
    """
    Resolve explicit supported values without hidden fallback.

    The function should map known enum/index/name values to the expected
    display target.
    """
    spec = display.get_display_spec(value)
    assert spec.name == expected


@pytest.mark.parametrize(
    "value",
    [
        2,
        -1,
        "unknown",
        "",
    ],
)
def test_get_display_spec_rejects_invalid_values(value: int | str) -> None:
    """
    Reject unsupported display values with a clear validation error.

    This prevents accidental drawing to front when callers pass wrong values.
    """
    with pytest.raises(ValueError):
        display.get_display_spec(value)
