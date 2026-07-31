from __future__ import annotations

import pytest

from busylib.types import InputKey
from examples.remote.keymap import KeyDecoder, default_keymap

ARROW_UP = b"\x1b[A"
ARROW_DOWN = b"\x1b[B"
SS3_UP = b"\x1bOA"
SS3_DOWN = b"\x1bOB"


def _decode(sequence: bytes) -> list[InputKey | None]:
    decoder = KeyDecoder(default_keymap())
    return [key for _raw, key in decoder.feed(sequence)]


@pytest.mark.parametrize(
    "sequence,expected",
    [
        (ARROW_UP, InputKey.DOWN),
        (ARROW_DOWN, InputKey.UP),
        (SS3_UP, InputKey.DOWN),
        (SS3_DOWN, InputKey.UP),
    ],
)
def test_arrow_keys_are_inverted_to_match_firmware_encoder_semantics(
    sequence: bytes, expected: InputKey
) -> None:
    """
    Arrow keys map to the opposite firmware key on purpose.

    The firmware treats `up`/`down` as encoder directions: every GUI widget
    focuses the *next* item on `InputKeyUp` (moving the highlight visually
    down) and the previous one on `InputKeyDown`. Inverting the arrows here
    makes the highlight follow the arrow actually pressed.
    """
    assert _decode(sequence) == [expected]


@pytest.mark.parametrize(
    "sequence,expected",
    [
        (b"\x1b[C", InputKey.OK),
        (b"\x1b[D", InputKey.BACK),
        (b"\r", InputKey.OK),
        (b" ", InputKey.START),
    ],
)
def test_non_arrow_bindings_are_unchanged(sequence: bytes, expected: InputKey) -> None:
    """
    Only the vertical arrows are inverted; other bindings map directly.
    """
    assert _decode(sequence) == [expected]
