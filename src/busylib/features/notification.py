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
from ..display import FRONT_DISPLAY, DisplaySpec
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

    Scrolling is the text element's own feature, so this only decides when
    to switch it on. The threshold is a character count rather than a
    measured width: glyph widths differ per font and the device does not
    report them, so a short line staying still matters more than being
    exact at the boundary.
    """
    if available <= 0:
        return None, None
    budget = max(1, SCROLL_THRESHOLD_CHARS * available // FRONT_DISPLAY.width)
    if len(text) <= budget:
        return None, None
    return available, SCROLL_RATE


@dataclass(frozen=True)
class NotificationSpec:
    """
    Everything a template needs, already resolved and validated.

    A template receives one of these rather than raw keyword arguments, so a
    custom template gets the icon already looked up, the geometry of the
    panel it is drawing on, and helpers for the parts that are easy to get
    wrong - text placement past an icon, and scrolling long lines.
    """

    line_1: str
    line_2: str | None = None
    icon: StockIcon | None = None
    font: types.DisplayFontName = DEFAULT_FONT
    line_1_color: types.ColorInput | None = None
    line_2_color: types.ColorInput | None = None
    background_color: types.ColorInput | None = None
    duration: int | None = None
    display: DisplaySpec = FRONT_DISPLAY

    @property
    def text_x(self) -> int:
        """
        Where text starts: past the icon, or at the plain left margin.

        The shipped icons are 5, 8 and 11px wide, so this is computed from
        the icon rather than fixed - a constant offset would overlap the
        narrow ones and leave a gap after the wide ones.
        """
        if self.icon is None:
            return TEXT_MARGIN
        return self.icon.width + ICON_TEXT_GAP

    @property
    def available_width(self) -> int:
        """
        How much width is left for text after the icon.
        """
        return self.display.width - self.text_x

    def text(
        self,
        element_id: str,
        text: str,
        *,
        y: int,
        align: str,
        color: types.ColorInput | None = None,
        x: int | None = None,
        width: int | None = None,
    ) -> types.TextElement:
        """
        Build a text element at `y`, scrolled if it cannot fit.

        `x` defaults to `text_x`, which is where a left-anchored line starts
        once the icon has had its share. A template anchoring to the right or
        the centre has to say where instead: with `mid_right` and the default
        x the line's right edge lands at the left margin, and the text runs
        off the panel.

        `width` is how much room the line has, and it is what scrolling is
        decided against. It defaults to everything right of `x`, which is
        only the room available when the line is anchored left - for any
        other anchor, pass it. Getting this wrong does not misplace the
        text, it scrolls it through a window a few pixels wide.
        """
        origin = self.text_x if x is None else x
        room = self.display.width - origin if width is None else width
        width, scroll_rate = _scroll(text, room)
        return types.TextElement(
            id=element_id,
            text=text,
            font=self.font,
            color=color,
            x=origin,
            y=y,
            align=align,  # type: ignore[arg-type]
            timeout=self.duration,
            display=self.display.name,
            width=width,
            scroll_rate=scroll_rate,
        )

    def icon_element(self, element_id: str = _ICON_ID) -> types.ImageElement | None:
        """
        Build the icon element, or None when there is no icon.
        """
        if self.icon is None:
            return None
        return types.ImageElement(
            id=element_id,
            stock_path=self.icon.path,
            x=0,
            y=self.display.height // 2,
            align="mid_left",
            timeout=self.duration,
            display=self.display.name,
        )


class Template(Protocol):
    """
    A way of arranging a notification on the panel.

    The built-in templates are ordinary implementations of this, so writing
    one is the same work: declare which fonts it can place, say when it
    applies, and return the elements. Everything version-dependent stays
    outside - the background fill is added by `build_notification`, which
    knows what the firmware can draw - so a template is only about layout.
    """

    @property
    def name(self) -> str:
        """
        Identifies the template in errors and logs.
        """
        ...

    @property
    def fonts(self) -> tuple[types.DisplayFontName, ...]:
        """
        The fonts this template can place without clipping.
        """
        ...

    def matches(self, spec: NotificationSpec) -> bool:
        """
        Whether this template suits the notification, for auto-selection.
        """
        ...

    def render(self, spec: NotificationSpec) -> list[types.DisplayElement]:
        """
        Lay the notification out as display elements.
        """
        ...


@dataclass(frozen=True)
class OneLineTemplate:
    """
    A single line centred vertically, with the icon to its left.
    """

    name: str = "one_line"
    fonts: tuple[types.DisplayFontName, ...] = ONE_LINE_FONTS

    def matches(self, spec: NotificationSpec) -> bool:
        return not spec.line_2

    def render(self, spec: NotificationSpec) -> list[types.DisplayElement]:
        elements: list[types.DisplayElement] = []
        icon = spec.icon_element()
        if icon is not None:
            elements.append(icon)
        elements.append(
            spec.text(
                _LINE_1_ID,
                spec.line_1,
                y=ONE_LINE_Y[spec.font],
                align="mid_left",
                color=spec.line_1_color,
            )
        )
        return elements


@dataclass(frozen=True)
class TwoLineTemplate:
    """
    Two lines anchored to the top and bottom edges, icon to their left.
    """

    name: str = "two_lines"
    fonts: tuple[types.DisplayFontName, ...] = TWO_LINE_FONTS

    def matches(self, spec: NotificationSpec) -> bool:
        return bool(spec.line_2)

    def render(self, spec: NotificationSpec) -> list[types.DisplayElement]:
        assert spec.line_2 is not None  # guaranteed by matches()
        top_y, bottom_y = TWO_LINE_Y[spec.font]
        elements: list[types.DisplayElement] = []
        icon = spec.icon_element()
        if icon is not None:
            elements.append(icon)
        elements.append(
            spec.text(
                _LINE_1_ID,
                spec.line_1,
                y=top_y,
                align="top_left",
                color=spec.line_1_color,
            )
        )
        elements.append(
            spec.text(
                _LINE_2_ID,
                spec.line_2,
                y=bottom_y,
                align="bottom_left",
                color=spec.line_2_color,
            )
        )
        return elements


ONE_LINE: Template = OneLineTemplate()
TWO_LINES: Template = TwoLineTemplate()

# Consulted in order, so the more specific template gets first refusal.
# There are two templates rather than one per layout: an icon only changes
# where text starts, which the spec works out, so "with an icon" is not a
# separate arrangement.
BUILT_IN_TEMPLATES: tuple[Template, ...] = (TWO_LINES, ONE_LINE)


def select_template(spec: NotificationSpec) -> Template:
    """
    Pick the built-in template that suits this notification.
    """
    for template in BUILT_IN_TEMPLATES:
        if template.matches(spec):
            return template
    raise ValueError("no built-in template matches this notification")


def background_element(
    spec: NotificationSpec,
    *,
    device_api_version: str | None = None,
    element_id: str = _BACKGROUND_ID,
) -> types.RectangleElement | None:
    """
    Build the background fill, or None when no background was asked for.

    Raises when the firmware cannot fill. A background colour is a filled
    rectangle, and that element enters the published API at 24.3.0
    (firmware 1.0.0-rc); below it there is none, which is why older
    integrations faked one by tiling a dense glyph across the panel. This
    library says so instead of carrying a second renderer.
    """
    if spec.background_color is None:
        return None
    if versioning.at_least(device_api_version, RECTANGLE_FILL_VERSION) is False:
        raise BusyBarFeatureUnavailableError(
            feature="background_color",
            required_version=RECTANGLE_FILL_VERSION,
            device_version=device_api_version,
        )
    return types.RectangleElement(
        id=element_id,
        x=0,
        y=0,
        width=spec.display.width,
        height=spec.display.height,
        fill="solid",
        fill_colors=[spec.background_color],
        border_width=0,
        timeout=spec.duration,
        display=spec.display.name,
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
    template: Template | None = None,
    display: DisplaySpec = FRONT_DISPLAY,
) -> types.DisplayElements:
    """
    Lay out a notification, with a built-in template or one of your own.

    Without `template`, the built-in that suits the arguments is chosen -
    two lines if a second was given, otherwise one. Pass `template` to use
    your own arrangement; it is handed the same `NotificationSpec` the
    built-ins get, so it does not have to redo icon lookup, text placement
    or scrolling.

    The background fill is added here rather than by the template, because
    whether the firmware can fill at all depends on its version, and that is
    exactly the part a caller should not have to know.

    `device_api_version` is what the bar reports. `None` means "unknown",
    and a current device is then assumed - guessing "old" would disable the
    feature for every caller that has not called `version()` yet.

    >>> elements = build_notification("Laundry done", icon="check")
    >>> len(elements.elements)
    2
    >>> elements.elements[0].type
    'image'
    >>> elements.elements[1].type
    'text'
    """
    resolved_icon: StockIcon | None = None
    if icon:
        resolved_icon = STOCK_ICONS.get(icon)
        if resolved_icon is None:
            raise ValueError(
                f"unknown icon {icon!r}; use one of {', '.join(sorted(STOCK_ICONS))}"
            )

    spec = NotificationSpec(
        line_1=line_1,
        line_2=line_2,
        icon=resolved_icon,
        font=font,
        line_1_color=line_1_color,
        line_2_color=line_2_color,
        background_color=background_color,
        duration=duration,
        display=display,
    )

    # An unrecognised font and a font the template cannot place are
    # different mistakes, and the second message would send someone hunting
    # for a template problem when they simply mistyped.
    if font not in ONE_LINE_FONTS:
        raise ValueError(
            f"unknown font {font!r}; use one of {', '.join(ONE_LINE_FONTS)}"
        )

    chosen = template if template is not None else select_template(spec)
    if font not in chosen.fonts:
        raise ValueError(
            f"font {font!r} does not fit the {chosen.name!r} template; use one of "
            f"{', '.join(chosen.fonts)}"
        )

    elements: list[types.DisplayElement] = []
    background = background_element(spec, device_api_version=device_api_version)
    if background is not None:
        elements.append(background)
    elements.extend(chosen.render(spec))

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
    template: Template | None = None,
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
        template=template,
    )
    return await client.display_draw(elements, application_name=application_name)
