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
from . import assets
from ..exceptions import BusyBarFeatureUnavailableError

logger = logging.getLogger(__name__)

# A background colour is drawn as a filled rectangle, which firmware below
# this version has no primitive for.
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
    An icon, with the width the layout has to reserve for it.

    `application` is set for one an application uploaded: the device
    resolves those inside that application's own folder, so the drawing
    names it by `path` rather than `stock_path` and the same file name in
    another application is another file.
    """

    path: str
    width: int
    application: str | None = None


# Icons shipped on the device. The path needs its sub-folder and extension -
# the flat "shared/<name>" form the OpenAPI spec suggests is refused.
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

# Where the bar keeps its assets, and the two directories icons live in.
# A draw request names an icon by the part of the path after the root -
# "shared/images/clock_5x5.image" - so the two forms are related but not
# the same, which is what these exist to keep straight.
ASSETS_ROOT = "/ext/apps_assets"
# Kept for callers that had it: the directories the firmware ships icons
# in. What `icons()` reads is wider than this now - every folder a bar
# holds images in, uploads included - and lives in `features.assets`.
ICON_DIRECTORIES = ("busy/images", "shared/images")

# The first bytes of a .image file: a four-byte marker, then width and
# height as little-endian 16-bit numbers. Verified against files whose size
# is also in their name - hourglass_11x11 reads 11 by 11 - which is what
# makes it safe to trust for the ones whose name says nothing, like the
# Draw Tool set.
_IMAGE_HEADER = 8
_IMAGE_WIDTH_AT = 4
_IMAGE_HEIGHT_AT = 6

# A PNG says its size in the IHDR chunk, sixteen bytes in.
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_HEADER = 24


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
    line_1_font: types.DisplayFontName = DEFAULT_FONT
    # The second line may be set in a size of its own. A short label over
    # a long one, or the other way round, says which of the two matters
    # in a way one size for both cannot.
    line_2_font: types.DisplayFontName | None = None
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
        font: types.DisplayFontName | None = None,
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
            font=self.line_1_font if font is None else font,
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
        uploaded = self.icon.application is not None
        return types.ImageElement(
            id=element_id,
            path=self.icon.path if uploaded else None,
            stock_path=None if uploaded else self.icon.path,
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
                y=ONE_LINE_Y[spec.line_1_font],
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
        # Each line is anchored to its own edge, so each takes the offset
        # its own font needs: the top from the top font's pair, the
        # bottom from the bottom font's.
        second = spec.line_2_font or spec.line_1_font
        top_y = TWO_LINE_Y[spec.line_1_font][0]
        bottom_y = TWO_LINE_Y[second][1]
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
                font=second,
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

    Raises below `RECTANGLE_FILL_VERSION`, where the firmware cannot fill.
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
    icon: str | StockIcon | None = None,
    line_1_font: types.DisplayFontName = DEFAULT_FONT,
    line_2_font: types.DisplayFontName | None = None,
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
    if isinstance(icon, StockIcon):
        # Already looked up - by `notify`, which can ask the bar about the
        # icons this layout knows nothing about.
        resolved_icon = icon
    elif icon:
        resolved_icon = STOCK_ICONS.get(icon)
        if resolved_icon is None:
            raise ValueError(
                f"unknown icon {icon!r}; use one of {', '.join(sorted(STOCK_ICONS))}"
                " - or call notify(), which can use any icon on the bar"
            )

    spec = NotificationSpec(
        line_1=line_1,
        line_2=line_2,
        icon=resolved_icon,
        line_1_font=line_1_font,
        line_2_font=line_2_font,
        line_1_color=line_1_color,
        line_2_color=line_2_color,
        background_color=background_color,
        duration=duration,
        display=display,
    )

    # An unrecognised font and a font the template cannot place are
    # different mistakes, and the second message would send someone hunting
    # for a template problem when they simply mistyped.
    for named in (line_1_font, line_2_font):
        if named is not None and named not in ONE_LINE_FONTS:
            raise ValueError(
                f"unknown font {named!r}; use one of {', '.join(ONE_LINE_FONTS)}"
            )

    chosen = template if template is not None else select_template(spec)
    # Both lines are checked, since each carries its own font and either
    # can be one the layout has no room for.
    for named in (line_1_font, line_2_font):
        if named is not None and named not in chosen.fonts:
            raise ValueError(
                f"font {named!r} does not fit the {chosen.name!r} template; use one of "
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


class IconCatalogueClient(Protocol):
    """
    What reading the bar's icons needs, which is less than the whole client.
    """

    async def storage_list(self, path: str) -> types.StorageList: ...

    async def storage_read(self, path: str) -> bytes: ...


async def icons(client: IconCatalogueClient) -> dict[str, str]:
    """
    Every icon this bar has, as a name and the path a drawing names it by.

    Icons are files, so this is not a fixed list: the firmware ships one
    set, the Draw Tool adds another, and an owner can upload their own or
    delete what they do not want. Reading it from the bar is the only way
    to be right about a particular bar - uploads included, which is what
    makes an icon somebody put there usable by name.

    The names are the file names without their extension, because that is
    what the bar calls them and what the Draw Tool shows. The friendly
    names in `STOCK_ICONS` stay as a short-hand for the handful worth
    having one.
    """
    return await assets.of_kind(client, "image")


def _dimensions(path: str, header: bytes) -> tuple[int, int]:
    """
    Read a file's own idea of its size, whichever format it is in.

    The firmware's `.image` carries width and height as little-endian
    shorts after a four-byte preamble; an upload is usually a PNG, whose
    IHDR puts them big-endian at sixteen bytes in. Both are read rather
    than assumed, because an icon's width is what the text is placed
    after - guess it and the two overlap.
    """
    if header.startswith(_PNG_SIGNATURE):
        if len(header) < _PNG_HEADER:
            raise ValueError(f"{path!r} is too short to be a PNG")
        return (
            int.from_bytes(header[16:20], "big"),
            int.from_bytes(header[20:24], "big"),
        )
    if len(header) < _IMAGE_HEADER:
        raise ValueError(f"{path!r} is too short to be an image")
    return (
        int.from_bytes(header[_IMAGE_WIDTH_AT : _IMAGE_WIDTH_AT + 2], "little"),
        int.from_bytes(header[_IMAGE_HEIGHT_AT : _IMAGE_HEIGHT_AT + 2], "little"),
    )


async def icon_at(
    client: IconCatalogueClient,
    reference: str,
    *,
    application_name: str | None = None,
    display: DisplaySpec = FRONT_DISPLAY,
) -> StockIcon:
    """
    Describe any image on the bar, including one somebody uploaded.

    An uploaded icon is a file like any other, so nothing is known about
    it in advance - not its size, and not whether it is an image at all.
    Both are settled here, from the file's own header, because the two
    ways this goes wrong are silent: an icon wider than the panel pushes
    the text off the display, and a file that is not an image draws
    nothing while every call reports success.

    Without `application_name`, `reference` is a shipped asset and carries
    its folder: `shared/images/clock_5x5.image`. With one, it is that
    application's own upload and is just the file name, the way the
    device resolves it.
    """
    if application_name is None:
        absolute = f"{ASSETS_ROOT}/{reference}"
    else:
        absolute = f"{assets.UPLOADS_ROOT}/{application_name}/{reference}"

    header = await client.storage_read(absolute)
    width, height = _dimensions(reference, bytes(header))
    if not 0 < width <= display.width or not 0 < height <= display.height:
        raise ValueError(
            f"{reference!r} is {width}x{height}, which does not fit the "
            f"{display.width}x{display.height} display"
        )
    return StockIcon(reference, width, application_name)


async def resolve_icon(
    client: IconCatalogueClient,
    name: str,
    *,
    application_name: str | None = None,
    display: DisplaySpec = FRONT_DISPLAY,
) -> StockIcon:
    """
    Resolve an icon name - or a path - to something a layout can use.

    The width is what a layout needs, and guessing it is how an icon and
    its text end up on top of each other: the Draw Tool's icons are 16
    wide where the built-in ones are 5, 8 or 11. Some file names carry
    their size and some do not, so it is read from the file itself.

    A friendly name from `STOCK_ICONS` is answered without asking the bar
    anything. Anything that looks like a path - it has a slash, or the
    `.image` extension - is read with `icon_at`, which is how an icon an
    owner uploaded can be used by name of file rather than by catalogue.
    """
    known = STOCK_ICONS.get(name)
    if known is not None:
        return known

    catalogue = await assets.discover_assets(client)
    for asset in catalogue:
        if asset.kind != "image":
            continue
        # An upload wins a name collision, and one belonging to the
        # application doing the drawing wins over another application's:
        # `path` is resolved inside the caller's own folder, so that is
        # the only upload this caller can actually draw.
        if asset.name != name and asset.reference != name:
            continue
        if asset.is_upload and asset.application != application_name:
            continue
        return await icon_at(
            client,
            asset.reference,
            application_name=asset.application,
            display=display,
        )

    available = sorted(
        asset.name
        for asset in catalogue
        if asset.kind == "image"
        and (not asset.is_upload or asset.application == application_name)
    )
    raise ValueError(f"this bar has no icon {name!r}; it has: {', '.join(available)}")


async def resolve_sound(
    client: IconCatalogueClient,
    name: str,
    *,
    application_name: str | None = None,
) -> assets.Asset:
    """
    Resolve a sound name to the asset a playback call can name.

    Same reasoning as `resolve_icon`: the three sounds with friendly
    names are a convenience, not the list - a bar holds the timer's own
    sounds too, and whatever an application uploaded. The short names in
    `STOCK_SOUNDS` are answered first and without asking the bar.
    """
    known = STOCK_SOUNDS.get(name)
    if known is not None:
        return assets.Asset(name=name, reference=known, kind="sound")

    catalogue = await assets.discover_assets(client)
    for asset in catalogue:
        if asset.kind != "sound":
            continue
        if asset.name != name and asset.reference != name:
            continue
        if asset.is_upload and asset.application != application_name:
            continue
        return asset

    available = sorted(
        asset.name
        for asset in catalogue
        if asset.kind == "sound"
        and (not asset.is_upload or asset.application == application_name)
    )
    raise ValueError(f"this bar has no sound {name!r}; it has: {', '.join(available)}")


class NotifyClient(IconCatalogueClient, Protocol):
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

    async def audio_play(
        self,
        *,
        path: str | None = None,
        stock_path: str | None = None,
        **request_kwargs: object,
    ) -> types.SuccessResponse:
        """
        Play a sound the bar holds, shipped or uploaded.
        """
        ...


async def notify(
    client: NotifyClient,
    line_1: str,
    *,
    line_2: str | None = None,
    icon: str | StockIcon | None = None,
    line_1_font: types.DisplayFontName = DEFAULT_FONT,
    line_2_font: types.DisplayFontName | None = None,
    line_1_color: types.ColorInput | None = None,
    line_2_color: types.ColorInput | None = None,
    background_color: types.ColorInput | None = None,
    sound: str | None = None,
    duration: int | None = None,
    priority: int = PRIORITY_DEFAULT,
    application_name: str = "busylib",
    template: Template | None = None,
) -> types.SuccessResponse:
    """
    Lay out a notification, draw it, and play its sound if it has one.

    A notification with a sound is one intention, so `sound` belongs here
    even though playing it is a second request - a caller composing this by
    hand has to remember both, and to pass the same `application_name` to
    each. Names come from `STOCK_SOUNDS`.

    The device version is taken from the client, so a caller cannot forget
    to pass it and silently lose the check that a feature the firmware lacks
    is refused rather than drawn wrong.

    There is deliberately no clearing helper: a drawing is withdrawn with
    `display_clear(application_name=...)`, which is already a single call to
    a single endpoint, and wrapping it would only add a synonym.

    Callers that want to place elements themselves can use
    `build_notification` and `display_draw` separately, or skip both.
    """
    logger.info(
        "notify line_2=%s icon=%s font=%s sound=%s",
        line_2 is not None,
        icon,
        line_1_font,
        sound,
    )
    # Any sound the bar has, for the same reason as the icons: the three
    # with friendly names are a convenience, and the timer's own sounds
    # and anything uploaded are equally playable.
    playable: assets.Asset | None = None
    if sound:
        playable = await resolve_sound(client, sound, application_name=application_name)

    # Any icon the bar has, not only the handful with a friendly name: the
    # Draw Tool's set is on the device too, and so is anything this
    # application uploaded - which is why the name is resolved against
    # this `application_name`, the folder the device will look in.
    # Resolving here rather than in the layout is what lets the width come
    # from the file instead of a guess. One already resolved is taken as
    # it is, so a caller that looked it up itself is not made to pay for
    # the lookup twice.
    resolved_icon: StockIcon | None = None
    if isinstance(icon, StockIcon):
        resolved_icon = icon
    elif icon:
        resolved_icon = await resolve_icon(
            client, icon, application_name=application_name
        )

    elements = build_notification(
        line_1,
        line_2=line_2,
        icon=resolved_icon,
        line_1_font=line_1_font,
        line_2_font=line_2_font,
        line_1_color=line_1_color,
        line_2_color=line_2_color,
        background_color=background_color,
        duration=duration,
        priority=priority,
        application_name=application_name,
        device_api_version=client.device_api_version,
        template=template,
    )
    drawn = await client.display_draw(elements, application_name=application_name)
    if playable is not None:
        await client.audio_play(
            stock_path=None if playable.is_upload else playable.reference,
            path=playable.reference if playable.is_upload else None,
            application_name=application_name,
        )
    return drawn
