"""
Composing a notification for the bar's front display.

The panel is 72x16 pixels, so a notification is not "some text" - it is a
handful of elements placed to the pixel, and the placement depends on the
font, on whether an icon takes the left edge, and on what the firmware in
front of you can draw. That knowledge belongs here rather than in each
caller: a Home Assistant integration, a script and a dashboard would
otherwise each rediscover the same offsets, and each get them subtly wrong
on a bar running different firmware.

This is a composed helper, not an endpoint: `notify()` takes a client and
ends up calling `display_draw`, which is the one-to-one wrapper around
POST /api/display/draw. Keeping it out of the client mixins keeps those
readable as the firmware API and nothing else.

The vertical offsets below were calibrated on real hardware. They are not
derivable from the font names: the draw fonts have different glyph metrics
and baselines, so the same anchor sits a pixel off for some of them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from .. import types, versioning
from ..display import FRONT_DISPLAY
from ..exceptions import BusyBarFeatureUnavailableError

logger = logging.getLogger(__name__)

# A filled rectangle is what a background colour is drawn with. It does not
# exist in every firmware: the element appears in the published API from
# 24.3.0 (firmware 1.0.0-rc) onwards and is absent at 23.3.0 and below,
# where a background had to be faked by tiling a dense glyph across the
# panel. Rather than carry that trick, callers are told plainly.
RECTANGLE_FILL_VERSION = "24.3.0"

DEFAULT_FONT: types.DisplayFontName = "small"

# Every font the one-line layout accepts.
ONE_LINE_FONTS: tuple[types.DisplayFontName, ...] = (
    "tiny",
    "small",
    "normal",
    "condensed",
    "bold",
    "large",
    "extra_large",
)

# Two lines only fit 16px in the shorter fonts, so the two tallest are
# offered for a single line only.
TWO_LINE_FONTS: tuple[types.DisplayFontName, ...] = (
    "tiny",
    "small",
    "normal",
    "condensed",
    "bold",
)

# One line is anchored `mid_left`. The centre of the panel is y=8, but most
# fonts read better a pixel higher; tiny and extra_large are already centred.
ONE_LINE_Y: dict[str, int] = {
    "tiny": 8,
    "small": 7,
    "normal": 7,
    "condensed": 7,
    "bold": 7,
    "large": 7,
    "extra_large": 8,
}

# Two lines anchor to `top_left` and `bottom_left`; each entry is
# (top_y, bottom_y). tiny pulls the lines together, the 9px fonts push them
# apart so they do not touch. Negative values are deliberate - the anchor is
# the panel edge, and the glyph box overhangs it.
TWO_LINE_Y: dict[str, tuple[int, int]] = {
    "tiny": (1, 15),
    "small": (0, 16),
    "normal": (-1, 17),
    "condensed": (-1, 17),
    "bold": (-1, 17),
}

# Gap between a left-aligned icon and the text after it.
ICON_TEXT_GAP = 2

# Left margin for text with no icon: flush against x=0 reads as clipped.
TEXT_MARGIN = 2

# scroll_rate is pixels per minute.
SCROLL_RATE = 1200

# Roughly how many characters of a small font cross the full 72px panel.
# Used only to decide whether a line needs scrolling at all; glyph widths
# differ per font and the device does not report them, so a short line
# staying still matters more than being exact at the boundary.
SCROLL_THRESHOLD_CHARS = 12


@dataclass(frozen=True)
class StockIcon:
    """
    A built-in icon, with the width the layout has to reserve for it.
    """

    path: str
    width: int


# Icons shipped on the device, verified present under
# /ext/apps_assets/shared/images. The path needs its sub-folder and its
# extension: the flat "shared/<name>" form in the OpenAPI spec does not
# resolve, and firmware answers 400 "Failed to decode image" for it.
#
# Widths differ - these are 5, 8 and 11px - so the text offset is computed
# from the icon rather than assumed, or an icon and its text overlap.
STOCK_ICONS: dict[str, StockIcon] = {
    "check": StockIcon("shared/images/checkmark_front_8x8.image", 8),
    "error": StockIcon("shared/images/error_front_8x8.image", 8),
    "info": StockIcon("shared/images/info_front_8x8.image", 8),
    "low_battery": StockIcon("shared/images/low_battery_front_8x8.image", 8),
    "clock": StockIcon("shared/images/clock_5x5.image", 5),
    "hourglass": StockIcon("shared/images/hourglass_5x5.image", 5),
    "start": StockIcon("shared/images/start_11x11.image", 11),
    "setup": StockIcon("shared/images/setup_11x11.image", 11),
}

# Built-in sounds, verified present under /ext/apps_assets/shared/sounds.
STOCK_SOUNDS: dict[str, str] = {
    "event": "shared/sounds/calendar_event_starts.snd",
    "reminder": "shared/sounds/calendar_reminder_ends.snd",
    "volume": "shared/sounds/volume_change.snd",
}

# A drawing is refused with "409 Not drawn due to low priority" by anything
# above it, so an ordinary notification sits mid-range and an interrupting
# one goes above a running Busy session.
PRIORITY_DEFAULT = 50
PRIORITY_INTERRUPT = 91

# The element id doubles as z-order on the device: higher sits on top. The
# background must be underneath, and foreground ids leave room to add
# elements later without renumbering.
_BACKGROUND_ID = "0"
_ICON_ID = "10"
_LINE_1_ID = "11"
_LINE_2_ID = "12"


def _scroll(text: str, available: int) -> tuple[int | None, int | None]:
    """
    Decide the (width, scroll_rate) that make a line scroll, or neither.

    Scrolling is the text element's own feature, so this only chooses when
    to switch it on.
    """
    if available <= 0:
        return None, None
    budget = max(1, SCROLL_THRESHOLD_CHARS * available // FRONT_DISPLAY.width)
    if len(text) <= budget:
        return None, None
    return available, SCROLL_RATE


def _line(
    element_id: str,
    text: str,
    *,
    font: types.DisplayFontName,
    color: types.ColorInput | None,
    x: int,
    y: int,
    align: str,
    duration: int | None,
) -> types.TextElement:
    """
    Build one line of a notification, scrolling it if it cannot fit.
    """
    width, scroll_rate = _scroll(text, FRONT_DISPLAY.width - x)
    return types.TextElement(
        id=element_id,
        text=text,
        font=font,
        color=color,
        x=x,
        y=y,
        align=align,  # type: ignore[arg-type]
        timeout=duration,
        display=types.DisplayName.FRONT,
        width=width,
        scroll_rate=scroll_rate,
    )


def build_notification(
    line_1: str,
    *,
    line_2: str | None = None,
    icon: str | None = None,
    font: types.DisplayFontName = DEFAULT_FONT,
    line_1_color: types.ColorInput | None = None,
    line_2_color: types.ColorInput | None = None,
    background_color: types.ColorInput | None = None,
    duration: int | None = None,
    priority: int = PRIORITY_DEFAULT,
    application_name: str = "busylib",
    device_api_version: str | None = None,
) -> types.DisplayElements:
    """
    Lay out a notification for the front display.

    Which of four layouts is used follows from the arguments - one line, one
    line with an icon, two lines, two lines with an icon - so a caller never
    supplies coordinates. On a 72x16 panel a wrong offset silently clips the
    text, which is the whole reason this is not left to callers.

    `device_api_version` is what the bar reports; pass it so a feature the
    firmware lacks is refused up front instead of drawing something wrong.
    `None` means "unknown", and the layout then assumes a current device -
    guessing "old" would degrade every caller that simply has not called
    `version()` yet.

    >>> elements = build_notification("Laundry done", icon="check")
    >>> [element.type for element in elements.elements]
    ['image', 'text']
    """
    if line_2 and font not in TWO_LINE_FONTS:
        raise ValueError(
            f"font {font!r} is too tall for two lines; use one of "
            f"{', '.join(TWO_LINE_FONTS)}, or send a single line"
        )
    if font not in ONE_LINE_FONTS:
        raise ValueError(
            f"unknown font {font!r}; use one of {', '.join(ONE_LINE_FONTS)}"
        )

    resolved_icon: StockIcon | None = None
    if icon:
        resolved_icon = STOCK_ICONS.get(icon)
        if resolved_icon is None:
            raise ValueError(
                f"unknown icon {icon!r}; use one of {', '.join(sorted(STOCK_ICONS))}"
            )

    elements: list[types.DisplayElement] = []

    if background_color is not None:
        if versioning.at_least(device_api_version, RECTANGLE_FILL_VERSION) is False:
            raise BusyBarFeatureUnavailableError(
                feature="background_color",
                required_version=RECTANGLE_FILL_VERSION,
                device_version=device_api_version,
            )
        elements.append(
            types.RectangleElement(
                id=_BACKGROUND_ID,
                x=0,
                y=0,
                width=FRONT_DISPLAY.width,
                height=FRONT_DISPLAY.height,
                fill="solid",
                fill_colors=[background_color],
                border_width=0,
                timeout=duration,
                display=types.DisplayName.FRONT,
            )
        )

    text_x = TEXT_MARGIN
    if resolved_icon is not None:
        text_x = resolved_icon.width + ICON_TEXT_GAP
        elements.append(
            types.ImageElement(
                id=_ICON_ID,
                stock_path=resolved_icon.path,
                x=0,
                y=FRONT_DISPLAY.height // 2,
                align="mid_left",
                timeout=duration,
                display=types.DisplayName.FRONT,
            )
        )

    if line_2:
        top_y, bottom_y = TWO_LINE_Y[font]
        elements.append(
            _line(
                _LINE_1_ID,
                line_1,
                font=font,
                color=line_1_color,
                x=text_x,
                y=top_y,
                align="top_left",
                duration=duration,
            )
        )
        elements.append(
            _line(
                _LINE_2_ID,
                line_2,
                font=font,
                color=line_2_color,
                x=text_x,
                y=bottom_y,
                align="bottom_left",
                duration=duration,
            )
        )
    else:
        elements.append(
            _line(
                _LINE_1_ID,
                line_1,
                font=font,
                color=line_1_color,
                x=text_x,
                y=ONE_LINE_Y[font],
                align="mid_left",
                duration=duration,
            )
        )

    return types.DisplayElements(
        application_name=application_name,
        priority=priority,
        elements=elements,
    )


class NotifyClient(Protocol):
    """
    The client surface a notification needs.

    Narrow on purpose: a Protocol rather than the concrete client keeps this
    module out of the import cycle the client would otherwise create, and
    makes the helper testable with a stub.
    """

    @property
    def device_api_version(self) -> str | None:
        """
        The API version the bar reported, or None if it has not been asked.
        """
        ...

    async def display_draw(
        self,
        display_data: types.DisplayElements | dict[str, object],
        **request_kwargs: object,
    ) -> types.SuccessResponse:
        """
        Send elements to the display.
        """
        ...


async def notify(
    client: NotifyClient,
    line_1: str,
    *,
    line_2: str | None = None,
    icon: str | None = None,
    font: types.DisplayFontName = DEFAULT_FONT,
    line_1_color: types.ColorInput | None = None,
    line_2_color: types.ColorInput | None = None,
    background_color: types.ColorInput | None = None,
    duration: int | None = None,
    priority: int = PRIORITY_DEFAULT,
    application_name: str = "busylib",
) -> types.SuccessResponse:
    """
    Lay out a notification and draw it on the bar.

    The device version is taken from the client, so a caller cannot forget
    to pass it and silently lose the check that a feature the firmware lacks
    is refused rather than drawn wrong.

    Callers that want to place elements themselves can use
    `build_notification` and `display_draw` separately, or skip both.
    """
    logger.info("notify line_2=%s icon=%s font=%s", line_2 is not None, icon, font)
    elements = build_notification(
        line_1,
        line_2=line_2,
        icon=icon,
        font=font,
        line_1_color=line_1_color,
        line_2_color=line_2_color,
        background_color=background_color,
        duration=duration,
        priority=priority,
        application_name=application_name,
        device_api_version=client.device_api_version,
    )
    return await client.display_draw(elements, application_name=application_name)
