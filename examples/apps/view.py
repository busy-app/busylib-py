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
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from busylib.frames import Frame

from .mirror import BUTTONS, KEYS, SWITCH
from .model import ManagerError


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
    A button on the remote. The keyboard is the other way in, and a button
    that took focus would swallow Enter and Space.
    """


class Remote(ModalScreen[None]):
    """
    The bar's display, and its keys and switch to press.
    """

    BINDINGS = [
        Binding("escape,v", "close", "Close"),
        Binding("enter", "press('ok')", "OK"),
        Binding("backspace", "press('back')", "Back"),
        Binding("space", "press('start')", "Start"),
        Binding("left", "press('left')", "◀", show=False),
        Binding("right", "press('right')", "▶", show=False),
        Binding("1", "press('busy')", "Busy", show=False),
        Binding("2", "press('custom')", "Custom", show=False),
        Binding("3", "press('off')", "Off", show=False),
        Binding("4", "press('apps')", "Apps", show=False),
        Binding("5", "press('settings')", "Settings", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(classes="dialog wide")

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("The bar", classes="title")
            yield BarScreen()
            with Horizontal(classes="pad"):
                for name, label, _ in BUTTONS:
                    yield Key(label, id=f"press-{name}")
            with Horizontal(classes="pad"):
                for name, label, _ in SWITCH:
                    yield Key(label, id=f"press-{name}", variant="primary")
            yield Static(
                "Enter OK · Backspace Back · Space Start · ◀ ▶ scroll · "
                "1-5 the switch · Esc close",
                classes="hint",
            )

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        name = (event.button.id or "").removeprefix("press-")
        self.action_press(name)

    def action_press(self, name: str) -> None:
        self.run_worker(self._press(name), group="press")

    async def _press(self, name: str) -> None:
        bar = self.app.manager.bar  # type: ignore[attr-defined]
        if bar is None:
            self.app.notify("There is no bar to press keys on", severity="warning")
            return
        try:
            await bar.press(KEYS[name])
        except ManagerError as err:
            self.app.notify(str(err), title="Could not press it", severity="error")

    def action_close(self) -> None:
        self.dismiss(None)
