"""
The bar's log on screen: fetched on demand, read a window at a time, searched.

A log can be long, and a screen shows a few dozen lines, so only a window of it
is in the text box: the newest lines to begin with, and more are added at
whichever end the cursor gets near. A search looks through all of it, not just
the window, and puts the window where the match is.
"""

from __future__ import annotations

import asyncio

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static, TextArea
from textual.widgets.text_area import Selection

from .logs import LogBuffer, unpack
from .model import ManagerError

# Lines in the box to begin with, and added each time the cursor nears an end.
CHUNK = 400
# How close to an end of the window the cursor has to get for more to be added.
EDGE = 30
# The most the box holds: past this, the end the cursor is farthest from is let go.
MOST = 4 * CHUNK


class LogScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("slash", "find", "Search"),
        Binding("n", "next(False)", "Next"),
        Binding("N", "next(True)", "Previous"),
        Binding("r", "reload", "Reload"),
        Binding("ctrl+home,g", "edge(False)", "Start", show=False),
        Binding("ctrl+end,G", "edge(True)", "End", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.buffer = LogBuffer([])
        # The window of the log that is in the box: lines [first, last).
        self.first = 0
        self.last = 0
        self.needle = ""
        # Where the last match was, to mark it again whenever the window is
        # redrawn: (line, column).
        self.mark: tuple[int, int] | None = None
        self.loaded = False
        # Set while the box is being filled, so that the cursor jumping is not
        # taken for a person scrolling.
        self._filling = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="log-status")
        yield TextArea("", id="log", read_only=True, soft_wrap=False)
        yield Input(placeholder="Search - Enter finds, n / N go on", id="find")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "Logs"
        self.query_one("#find", Input).display = False
        self.query_one("#log", TextArea).focus()
        self.say("Asking the bar for its log...")
        self.run_worker(self.load(), exclusive=True, group="log")

    # Getting it --------------------------------------------------------

    async def load(self) -> None:
        bar = self.app.manager.bar  # type: ignore[attr-defined]
        try:
            if bar is None:
                raise ManagerError("there is no bar to read logs from")
            data = await bar.fetch_log()
            text = await asyncio.to_thread(unpack, data)
        except ManagerError as err:
            self.say(f"Could not get the log: {err}. Press r to try again.")
            return
        self.buffer = LogBuffer.of(text)
        self.loaded = True
        if not self.buffer.lines:
            self.say("The log is empty. Press r to read it again.")
            return
        total = len(self.buffer)
        self.fill(max(0, total - CHUNK), total, focus=total - 1)

    def say(self, text: str) -> None:
        self.query_one("#log-status", Static).update(text)

    # The window --------------------------------------------------------

    def fill(self, first: int, last: int, focus: int) -> None:
        """
        Put lines [first, last) in the box with the cursor on line `focus`,
        and mark the last match if it is among them.
        """
        self.first, self.last = first, last
        area = self.query_one("#log", TextArea)
        self._filling = True
        area.load_text("\n".join(self.buffer.lines[first:last]))
        row = min(max(focus - first, 0), last - first - 1)
        if self.mark is not None and first <= self.mark[0] < last:
            line, column = self.mark
            start = (line - first, column)
            area.selection = Selection(start, (start[0], column + len(self.needle)))
            area.scroll_cursor_visible(center=True)
        else:
            area.move_cursor((row, 0), center=True)
        # Messages about the cursor having moved arrive after this returns.
        self.call_after_refresh(self._done_filling)
        self.status()

    def _done_filling(self) -> None:
        self._filling = False

    def status(self) -> None:
        total = len(self.buffer)
        row = self.query_one("#log", TextArea).cursor_location[0]
        text = f"Line {self.first + row + 1} of {total}"
        if self.first or self.last < total:
            text += f" · showing {self.first + 1}-{self.last}, more loads as you scroll"
        if self.needle:
            hits = self.buffer.count(self.needle)
            text += f" · {hits} line(s) with {self.needle!r}"
        self.say(text)

    @on(TextArea.SelectionChanged)
    def moved(self) -> None:
        """
        Add lines at whichever end of the window the cursor has come near.
        """
        if self._filling or not self.loaded:
            return
        area = self.query_one("#log", TextArea)
        row = area.cursor_location[0]
        line = self.first + row
        total = len(self.buffer)
        first, last = self.first, self.last
        if row < EDGE and first > 0:
            first = max(0, first - CHUNK)
            last = min(last, first + MOST)
        elif row > last - first - EDGE and last < total:
            last = min(total, last + CHUNK)
            first = max(first, last - MOST)
        else:
            self.status()
            return
        self.fill(first, last, focus=line)

    # Searching ---------------------------------------------------------

    def action_find(self) -> None:
        box = self.query_one("#find", Input)
        box.display = True
        box.value = self.needle
        box.focus()

    @on(Input.Submitted, "#find")
    def submitted(self, event: Input.Submitted) -> None:
        self.needle = event.value.strip()
        box = self.query_one("#find", Input)
        box.display = False
        self.query_one("#log", TextArea).focus()
        if self.needle:
            self.action_next(False, at_cursor=True)
        else:
            self.mark = None
            self.status()

    def action_next(self, backwards: bool, at_cursor: bool = False) -> None:
        """
        Go to the next line with what was searched for - through the whole
        log, not only what is in the box.
        """
        if not self.needle:
            self.action_find()
            return
        total = len(self.buffer)
        if not total:
            return
        row = self.query_one("#log", TextArea).cursor_location[0]
        here = self.first + row
        start = here if at_cursor else here + (-1 if backwards else 1)
        found = self.buffer.find(self.needle, start % total, backwards=backwards)
        if found is None:
            self.mark = None
            self.app.notify(f"No line has {self.needle!r}", severity="warning")
            return
        column = self.buffer.lines[found].lower().find(self.needle.lower())
        self.mark = (found, column)
        if self.first <= found < self.last:
            area = self.query_one("#log", TextArea)
            self._filling = True
            start_at = (found - self.first, column)
            area.selection = Selection(
                start_at, (start_at[0], column + len(self.needle))
            )
            area.scroll_cursor_visible(center=True)
            self.call_after_refresh(self._done_filling)
            self.status()
        else:
            first = max(0, min(found - CHUNK // 2, total - CHUNK))
            self.fill(first, min(total, first + CHUNK), focus=found)

    def action_edge(self, end: bool) -> None:
        """
        Jump to the very start of the log, or the very end.
        """
        total = len(self.buffer)
        if not total:
            return
        self.mark = None
        if end:
            self.fill(max(0, total - CHUNK), total, focus=total - 1)
        else:
            self.fill(0, min(total, CHUNK), focus=0)

    # Leaving and reloading ---------------------------------------------

    def action_reload(self) -> None:
        self.say("Asking the bar for its log...")
        self.run_worker(self.load(), exclusive=True, group="log")

    def action_back(self) -> None:
        box = self.query_one("#find", Input)
        if box.display:
            box.display = False
            self.query_one("#log", TextArea).focus()
            return
        self.dismiss(None)
