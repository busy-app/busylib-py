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


def get_display_spec(
    display: DisplaySpec | DisplayName | int | str | None,
) -> DisplaySpec:
    """
    Resolve a display spec using explicit front/back selection.

    `front` is used only when display is None. Any unsupported display value
    raises ValueError to avoid silently rendering to the wrong screen.
    """
    if isinstance(display, DisplaySpec):
        return display
    if display is None:
        return FRONT_DISPLAY
    if isinstance(display, DisplayName):
        return _DISPLAY_BY_NAME[display]
    if isinstance(display, int):
        if display in _DISPLAY_BY_INDEX:
            return _DISPLAY_BY_INDEX[display]
        raise ValueError(f"Unsupported display index: {display}")
    if isinstance(display, str):
        display_lower = display.strip().lower()
        for name, spec in _DISPLAY_BY_NAME.items():
            if name.value == display_lower:
                return spec
        raise ValueError(f"Unsupported display name: {display}")
    raise ValueError(f"Unsupported display value type: {type(display).__name__}")
