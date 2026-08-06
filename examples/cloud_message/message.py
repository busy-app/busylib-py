from __future__ import annotations

from dataclasses import dataclass

from busylib import types

from examples.cloud_message.colors import parse_color

APPLICATION_NAME = "cloud_message"

# The front display is a 72x16 RGB LED matrix.
FRONT_WIDTH = 72
FRONT_HEIGHT = 16

# System app priorities: stub/poweroff 0, built-in apps 10, an active
# BUSY/CUSTOM work session 90. Default above 90 so a deliberate notification
# is not silently rejected with 409 while the owner is in a session.
DEFAULT_PRIORITY = 95

# A filled rectangle is composited over text regardless of element order, so it
# cannot act as an opaque backdrop. Overlaying it with alpha tints the whole
# display while keeping the text brighter than the background, which reads as
# coloured-background text. Fully opaque fills hide the text entirely.
DEFAULT_BACKGROUND_ALPHA = 0x55


@dataclass(frozen=True)
class Message:
    """
    A single glanceable status line to show on the front display.
    """

    text: str
    color: str = "white"
    background: str | None = None
    led: str | None = None
    font: str = "normal"
    scroll: bool = True
    priority: int = DEFAULT_PRIORITY

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("message text must not be empty")
        # Fonts are bitmap ASCII, so anything outside printable ASCII is
        # rejected by the device rather than rendered.
        if any(not 0x20 <= ord(char) <= 0x7E for char in self.text):
            raise ValueError("message text must be printable ASCII")
        if not 1 <= self.priority <= 100:
            raise ValueError("priority must be between 1 and 100")


def build_elements(message: Message) -> types.DisplayElements:
    """
    Turn a `Message` into a validated display payload.
    """
    text_element: dict[str, object] = {
        "id": "msg",
        "type": "text",
        "x": 0,
        "y": 4,
        "text": message.text,
        "font": message.font,
        "color": parse_color(message.color),
    }
    if message.scroll:
        # Anything wider than the display has to scroll to be readable.
        text_element.update(
            width=FRONT_WIDTH,
            scroll_rate=600,
            scroll_start_delay=500,
        )

    elements: list[dict[str, object]] = [text_element]
    if message.background:
        elements.append(
            {
                "id": "bg",
                "type": "rectangle",
                "x": 0,
                "y": 0,
                "align": "top_left",
                "display": "front",
                "width": FRONT_WIDTH,
                "height": FRONT_HEIGHT,
                "fill": "solid",
                "fill_colors": [
                    parse_color(
                        message.background,
                        default_alpha=DEFAULT_BACKGROUND_ALPHA,
                    )
                ],
                "border_width": 0,
            }
        )

    payload: dict[str, object] = {
        "application_name": APPLICATION_NAME,
        "priority": message.priority,
        "elements": elements,
    }
    if message.led:
        payload["led_notification_color"] = parse_color(message.led)

    return types.DisplayElements.model_validate(payload)
