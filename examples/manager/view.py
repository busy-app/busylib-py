"""
The bar's display in the terminal, and a remote for the bar.

The picture is the front display drawn with half blocks: each character cell
holds two pixels, the upper as its colour and the lower as its background, so
the 72x16 panel fits in 72x8 cells with square pixels.
"""

from __future__ import annotations

from functools import lru_cache

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from busylib.frames import Frame

from .mirror import BUTTONS, SWITCH


@lru_cache(maxsize=4096)
def _style(top: bytes, bottom: bytes) -> Style:
    return Style(color=Color.from_rgb(*top), bgcolor=Color.from_rgb(*bottom))


def draw(frame: Frame) -> Text:
    """
    A frame as text: one line per two rows of pixels.
    """
    text = Text(no_wrap=True, overflow="crop")
    rows = frame.rows()
    pairs = len(rows) // 2
    for line in range(pairs):
        upper, lower = rows[2 * line], rows[2 * line + 1]
        for x in range(0, len(upper), 3):
            text.append("▀", _style(upper[x : x + 3], lower[x : x + 3]))
        if line < pairs - 1:
            text.append("\n")
    return text


class BarScreen(Static):
    """
    What the bar's front display shows now, as far as the stream has said.
    """

    def __init__(self) -> None:
        super().__init__("", classes="bar-screen")
        self._seen = -1

    def on_mount(self) -> None:
        self.set_interval(0.1, self.sync)
        self.sync()

    def sync(self) -> None:
        mirror = self.app.mirror  # type: ignore[attr-defined]
        if mirror.version == self._seen:
            return
        self._seen = mirror.version
        if mirror.frame is None:
            self.update(Text(self.app.screen_note, style="dim"))  # type: ignore[attr-defined]
        else:
            self.update(draw(mirror.frame))


class Key(Button, can_focus=False):
    """
    A button of the pad. The keyboard is the other way in, and a button that
    took focus would swallow Enter and Space.
    """


# What the keys do on the main screen, which the pad's hint repeats.
HINT = (
    "[b]Backspace[/b] Back · [b]k[/b] OK · [b]Space[/b] Start\n"
    "[b]\\[[/b] [b]][/b] scroll · [b]1[/b]-[b]5[/b] the switch"
)


class Pad(Vertical):
    """
    The bar's keys and switch, to click - and the keys that press them.
    """

    def compose(self) -> ComposeResult:
        with Horizontal(classes="row"):
            for name, label, _ in BUTTONS:
                yield Key(label, id=f"press-{name}")
        with Horizontal(classes="row"):
            for name, label, _ in SWITCH:
                yield Key(label, id=f"press-{name}", variant="primary")
        yield Static(HINT, classes="hint")
