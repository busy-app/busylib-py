from __future__ import annotations

import pytest

from busylib import types
from busylib.features import notification
from busylib.display import FRONT_DISPLAY
from busylib.exceptions import BusyBarFeatureUnavailableError


def _kinds(elements: types.DisplayElements) -> list[str]:
    return [element.type for element in elements.elements]


def _texts(elements: types.DisplayElements) -> list[types.TextElement]:
    return [e for e in elements.elements if isinstance(e, types.TextElement)]


def _rectangles(elements: types.DisplayElements) -> list[types.RectangleElement]:
    return [e for e in elements.elements if isinstance(e, types.RectangleElement)]


def test_the_layout_follows_from_the_fields_given() -> None:
    """
    Four templates, chosen here rather than by the caller.

    This is the whole point of the module: an automation author says what to
    show, not where. The panel is 72x16, so a wrong offset silently clips
    the text instead of failing.
    """
    assert _kinds(notification.build_notification("one")) == ["text"]
    assert _kinds(notification.build_notification("one", icon="check")) == [
        "image",
        "text",
    ]
    assert _kinds(notification.build_notification("one", line_2="two")) == [
        "text",
        "text",
    ]
    assert _kinds(
        notification.build_notification("one", line_2="two", icon="check")
    ) == ["image", "text", "text"]


@pytest.mark.parametrize(
    "icon,width",
    [("clock", 5), ("check", 8), ("start", 11)],
)
def test_text_starts_past_the_icon_whatever_its_width(icon: str, width: int) -> None:
    """
    The shipped icons are 5, 8 and 11px wide, so the offset is computed.

    A fixed offset would overlap the narrow icons or leave a gap after the
    wide ones, and the device reports no icon dimensions to discover this at
    runtime.
    """
    elements = notification.build_notification("hello", icon=icon)
    text = _texts(elements)[0]

    assert text.x == width + notification.ICON_TEXT_GAP


def test_text_keeps_a_margin_when_there_is_no_icon() -> None:
    """
    Flush against x=0 reads as clipped, so a small margin stays.
    """
    text = _texts(notification.build_notification("hello"))[0]

    assert text.x == notification.TEXT_MARGIN


def test_two_lines_anchor_to_opposite_edges() -> None:
    """
    Line 1 hangs off the top, line 2 off the bottom.

    Anchoring each line to its own edge is what makes the same table work
    for fonts of different heights.
    """
    top, bottom = _texts(
        notification.build_notification("one", line_2="two", font="small")
    )

    assert (top.align, bottom.align) == ("top_left", "bottom_left")
    assert (top.y, bottom.y) == notification.TWO_LINE_Y["small"]


def test_a_single_line_is_centred_for_its_font() -> None:
    """
    The vertical offsets are per-font and calibrated, not derived.
    """
    for font in notification.ONE_LINE_FONTS:
        text = _texts(notification.build_notification("hi", font=font))[0]
        assert text.align == "mid_left"
        assert text.y == notification.ONE_LINE_Y[font]


def test_tall_fonts_are_refused_for_two_lines() -> None:
    """
    Two lines do not fit 16px in the tallest fonts.

    Refused rather than quietly substituted: a caller who asked for `large`
    and got `small` has no way to notice.
    """
    for font in ("large", "extra_large"):
        assert font in notification.ONE_LINE_FONTS
        assert font not in notification.TWO_LINE_FONTS
        with pytest.raises(ValueError, match="does not fit the 'two_lines' template"):
            notification.build_notification("one", line_2="two", font=font)


def test_unknown_fonts_and_icons_are_refused_before_the_request() -> None:
    """
    Fail here, with the valid values, rather than on a device 400.

    An unresolvable icon path comes back as "Failed to decode image", which
    says nothing about which names exist.
    """
    with pytest.raises(ValueError, match="unknown font"):
        notification.build_notification("hi", font="comic-sans")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown icon"):
        notification.build_notification("hi", icon="nope")


def test_only_overflowing_text_scrolls() -> None:
    """
    Scrolling is the text element's own feature; this decides when.

    A short line that crawls across the panel is worse than one that sits
    still, so the switch is off until the text cannot fit.
    """
    short = _texts(notification.build_notification("hi"))[0]
    assert short.scroll_rate is None
    assert short.width is None

    long_text = _texts(
        notification.build_notification("a considerably longer message")
    )[0]
    assert long_text.scroll_rate == notification.SCROLL_RATE
    assert long_text.width == FRONT_DISPLAY.width - notification.TEXT_MARGIN


def test_an_icon_lowers_the_bar_for_scrolling() -> None:
    """
    An icon takes width from the text, so it overflows sooner.
    """
    text = "medium length"
    without = _texts(notification.build_notification(text))[0]
    with_icon = _texts(notification.build_notification(text, icon="start"))[0]

    assert with_icon.width is not None
    assert with_icon.width == FRONT_DISPLAY.width - with_icon.x
    assert without.width is None or without.width > with_icon.width


def test_a_background_covers_the_panel_below_everything_else() -> None:
    """
    The element id doubles as z-order on the device: higher draws on top.
    """
    elements = notification.build_notification(
        "hi", background_color=[0, 0, 90], icon="check"
    )
    background = _rectangles(elements)[0]

    assert (background.width, background.height) == (
        FRONT_DISPLAY.width,
        FRONT_DISPLAY.height,
    )
    assert background.fill == "solid"
    ids = [int(element.id) for element in elements.elements]
    assert ids == sorted(ids), "background must carry the lowest id"
    assert int(background.id) < min(
        int(element.id) for element in elements.elements if element.type != "rectangle"
    )


def test_colours_are_accepted_as_rgb_and_normalised() -> None:
    """
    Callers pass an RGB triple; the wire wants #RRGGBBAA.
    """
    elements = notification.build_notification(
        "hi", line_1_color=[255, 80, 80], background_color=[0, 0, 90]
    )

    assert _texts(elements)[0].color == "#FF5050FF"
    assert _rectangles(elements)[0].fill_colors == ["#00005AFF"]


def test_a_background_is_refused_on_firmware_that_cannot_fill() -> None:
    """
    The rectangle element enters the published API at 24.3.0.

    Older firmware needed a background faked by tiling a dense glyph across
    the panel. Carrying that would mean maintaining a second renderer, so
    the caller is told to update instead.
    """
    with pytest.raises(BusyBarFeatureUnavailableError) as exc:
        notification.build_notification(
            "hi", background_color=[0, 0, 90], device_api_version="23.3.0"
        )

    assert exc.value.required_version == notification.RECTANGLE_FILL_VERSION
    assert exc.value.device_version == "23.3.0"

    # At the floor and above it draws normally.
    for version in ("24.3.0", "27.7.0"):
        elements = notification.build_notification(
            "hi", background_color=[0, 0, 90], device_api_version=version
        )
        assert _rectangles(elements)


def test_an_unknown_device_version_is_treated_as_current() -> None:
    """
    Unknown is not the same as old.

    A client that has not called `version()` yet knows nothing about the
    bar, and assuming "old" would disable the feature for every caller who
    simply never asked.
    """
    elements = notification.build_notification("hi", background_color=[0, 0, 90])

    assert _rectangles(elements)


def test_the_priorities_sit_where_the_device_arbitrates() -> None:
    """
    A drawing below the current owner is refused with a 409.
    """
    assert 1 <= notification.PRIORITY_DEFAULT <= 100
    assert notification.PRIORITY_INTERRUPT > notification.PRIORITY_DEFAULT
    assert notification.build_notification("hi").priority == (
        notification.PRIORITY_DEFAULT
    )


class StubClient:
    """
    Records what `notify` sends, standing in for a real client.
    """

    def __init__(self, device_api_version: str | None) -> None:
        self._version = device_api_version
        self.drawn: types.DisplayElements | None = None
        self.request_kwargs: dict[str, object] = {}
        self.played: str | None = None
        self.play_kwargs: dict[str, object] = {}

    @property
    def device_api_version(self) -> str | None:
        return self._version

    async def display_draw(
        self,
        display_data: types.DisplayElements | dict[str, object],
        **request_kwargs: object,
    ) -> types.SuccessResponse:
        assert isinstance(display_data, types.DisplayElements)
        self.drawn = display_data
        self.request_kwargs = request_kwargs
        return types.SuccessResponse(result="OK")

    async def audio_play(
        self,
        *,
        stock_path: str | None = None,
        **request_kwargs: object,
    ) -> types.SuccessResponse:
        self.played = stock_path
        self.play_kwargs = request_kwargs
        return types.SuccessResponse(result="OK")


async def test_notify_draws_what_the_layout_produced() -> None:
    """
    The helper composes; it does not reimplement the layout.
    """
    client = StubClient("27.7.0")

    result = await notification.notify(
        client, "Laundry", icon="check", application_name="home_assistant"
    )

    assert result.result == "OK"
    assert client.drawn is not None
    assert [element.type for element in client.drawn.elements] == ["image", "text"]
    assert client.drawn.application_name == "home_assistant"
    assert client.request_kwargs["application_name"] == "home_assistant"


async def test_notify_takes_the_device_version_from_the_client() -> None:
    """
    The version check cannot be forgotten by the caller.

    This is the reason the helper exists at all rather than leaving callers
    to call `build_notification` themselves: a caller who forgets to pass
    the version loses the guard silently, and draws a background on
    firmware that cannot fill.
    """
    old = StubClient("23.3.0")

    with pytest.raises(BusyBarFeatureUnavailableError):
        await notification.notify(old, "hi", background_color=[0, 0, 90])

    assert old.drawn is None, "nothing should reach the device"

    current = StubClient("27.7.0")
    await notification.notify(current, "hi", background_color=[0, 0, 90])
    assert current.drawn is not None


class CentredTemplate:
    """
    A user-written template: one line, centred, ignoring any icon.

    Written the way the docs describe, to prove the same shape works from
    outside the library.
    """

    name = "centred"
    fonts = ("small", "bold")

    def matches(self, spec: notification.NotificationSpec) -> bool:
        return True

    def render(self, spec: notification.NotificationSpec) -> list[types.DisplayElement]:
        return [spec.text("1", spec.line_1, y=8, align="center")]


def test_a_custom_template_replaces_the_built_in_choice() -> None:
    """
    A template passed in is used instead of the auto-selected one.
    """
    elements = notification.build_notification(
        "hello", template=CentredTemplate()
    ).elements

    assert len(elements) == 1
    assert elements[0].align == "center"


def test_a_custom_template_gets_the_resolved_icon_and_geometry() -> None:
    """
    The spec hands a template the work it should not repeat.

    Icon lookup and the text offset past it are the parts that are easy to
    get wrong, so they arrive already done - a template that wants the icon
    only has to ask for the element.
    """
    seen: list[notification.NotificationSpec] = []

    class Recording(CentredTemplate):
        def render(
            self, spec: notification.NotificationSpec
        ) -> list[types.DisplayElement]:
            seen.append(spec)
            return super().render(spec)

    notification.build_notification("hello", icon="start", template=Recording())

    spec = seen[0]
    assert spec.icon is not None
    assert spec.icon.width == 11, "the 11px icon, resolved from its name"
    assert spec.text_x == 11 + notification.ICON_TEXT_GAP
    assert spec.available_width == spec.display.width - spec.text_x
    assert spec.icon_element() is not None


def test_a_custom_template_declares_which_fonts_it_can_place() -> None:
    """
    The font check applies to a custom template on its own terms.
    """
    notification.build_notification("hi", font="bold", template=CentredTemplate())

    with pytest.raises(ValueError, match="does not fit the 'centred' template"):
        notification.build_notification("hi", font="tiny", template=CentredTemplate())


def test_the_background_is_added_for_a_custom_template_too() -> None:
    """
    A template never has to know what the firmware can fill.

    The version-gated part stays outside the template, so a user-written one
    cannot forget it and draw a background on firmware without a fill.
    """
    elements = notification.build_notification(
        "hi",
        background_color=[0, 0, 90],
        template=CentredTemplate(),
        device_api_version="27.7.0",
    ).elements

    assert [element.type for element in elements] == ["rectangle", "text"]

    with pytest.raises(BusyBarFeatureUnavailableError):
        notification.build_notification(
            "hi",
            background_color=[0, 0, 90],
            template=CentredTemplate(),
            device_api_version="23.3.0",
        )


def test_select_template_prefers_the_more_specific_arrangement() -> None:
    """
    Two lines win over one when a second line was given.
    """
    one = notification.NotificationSpec(line_1="a")
    two = notification.NotificationSpec(line_1="a", line_2="b")

    assert notification.select_template(one).name == "one_line"
    assert notification.select_template(two).name == "two_lines"


def test_a_line_scrolls_against_the_room_it_was_given() -> None:
    """
    The scroll window follows `width`, not the space right of `x`.

    Both defaults assume a left-anchored line. A right-anchored template
    that takes them gets a line scrolling through a two-pixel window - found
    on real hardware, where "CUSTOM" rendered as six lit pixels.
    """
    spec = notification.NotificationSpec(line_1="CUSTOM")
    right = spec.display.width - 2

    naive = spec.text("1", "CUSTOM", y=8, align="mid_right", x=right)
    assert naive.width == 2, "the inferred room right of x is tiny"
    assert naive.scroll_rate == notification.SCROLL_RATE

    told = spec.text("1", "CUSTOM", y=8, align="mid_right", x=right, width=right)
    assert told.width is None, "it fits, so it must not scroll"
    assert told.scroll_rate is None
    assert told.x == right


async def test_notify_plays_the_sound_with_the_same_application_name() -> None:
    """
    Sound and drawing arrive as one intention, owned by one application.

    Playing it is a second request, and the application name has to match
    the drawing's or the two belong to different owners on the device.
    """
    client = StubClient("27.7.0")

    await notification.notify(
        client, "Laundry", sound="event", application_name="home_assistant"
    )

    assert client.played == notification.STOCK_SOUNDS["event"]
    assert client.play_kwargs["application_name"] == "home_assistant"


async def test_notify_without_a_sound_plays_nothing() -> None:
    """
    The extra request only happens when a sound was asked for.
    """
    client = StubClient("27.7.0")

    await notification.notify(client, "Laundry")

    assert client.drawn is not None
    assert client.played is None


async def test_notify_refuses_an_unknown_sound_before_drawing() -> None:
    """
    A mistyped sound fails outright rather than drawing silently.
    """
    client = StubClient("27.7.0")

    with pytest.raises(ValueError, match="unknown sound"):
        await notification.notify(client, "Laundry", sound="fanfare")

    assert client.drawn is None, "nothing should reach the device"
