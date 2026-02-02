from __future__ import annotations

from dataclasses import dataclass

from .types import DisplayName


@dataclass(frozen=True)
class DisplaySpec:
    name: DisplayName
    index: int
    width: int
    height: int
    description: str


FRONT_DISPLAY = DisplaySpec(
    name=DisplayName.FRONT,
    index=0,
    width=72,
    height=16,
    description="72x16 RGB LED matrix, ~16M colors, >800 nits",
)

BACK_DISPLAY = DisplaySpec(
    name=DisplayName.BACK,
    index=1,
    width=160,
    height=80,
    description="160x80 monochrome OLED, 16 gray scales",
)


_DISPLAY_BY_NAME = {
    DisplayName.FRONT: FRONT_DISPLAY,
    DisplayName.BACK: BACK_DISPLAY,
}

_DISPLAY_BY_INDEX = {
    0: FRONT_DISPLAY,
    1: BACK_DISPLAY,
}


def get_display_spec(display: DisplayName | int | str | None) -> DisplaySpec:
    """
    Resolve display spec by enum, index, or string.
    Defaults to FRONT display when None/unknown.
    """
    if isinstance(display, DisplaySpec):
        return display
    if isinstance(display, DisplayName):
        return _DISPLAY_BY_NAME.get(display, FRONT_DISPLAY)
    if isinstance(display, int):
        return _DISPLAY_BY_INDEX.get(display, FRONT_DISPLAY)
    if isinstance(display, str):
        display_lower = display.lower()
        for spec in _DISPLAY_BY_NAME.values():
            if spec.name.value == display_lower:
                return spec
    return FRONT_DISPLAY
