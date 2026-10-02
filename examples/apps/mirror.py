"""
A picture of the bar's front display, and the keys that drive it.

The bar streams its display as part of the status stream the manager already
holds open to know the bar is there. This keeps the newest frame from it and
says when it changed; drawing it is the interface's business.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from busylib import types
from busylib.frames import Frame

# What the interface offers to press, as (name, label, key). The HTTP API
# calls the scroll keys up and down; what a person sees is the selection
# moving sideways, and the firmware turns "up" into "focus the next item" - so
# "right" is up and "left" is down.
BUTTONS: tuple[tuple[str, str, types.InputKey], ...] = (
    ("back", "Back", types.InputKey.BACK),
    ("ok", "OK", types.InputKey.OK),
    ("start", "Start", types.InputKey.START),
    ("left", "◀", types.InputKey.DOWN),
    ("right", "▶", types.InputKey.UP),
)

# The switch's five positions, in the order they sit on the bar.
SWITCH: tuple[tuple[str, str, types.InputKey], ...] = (
    ("busy", "Busy", types.InputKey.BUSY),
    ("custom", "Custom", types.InputKey.CUSTOM),
    ("off", "Off", types.InputKey.OFF),
    ("apps", "Apps", types.InputKey.APPS),
    ("settings", "Settings", types.InputKey.SETTINGS),
)

KEYS: dict[str, types.InputKey] = {name: key for name, _, key in (*BUTTONS, *SWITCH)}


class Mirror:
    """
    The newest frame of the front display.

    `version` rises with every change, so a widget that redraws on a timer
    can tell whether there is anything new without comparing pictures.
    """

    def __init__(self) -> None:
        self.frame: Frame | None = None
        self.version = 0

    def feed(self, message: Mapping[str, Any]) -> None:
        """
        Take the frame out of a status message, if it carries one.

        A frame that cannot be read is skipped: one bad frame must not stop
        the display, and the next one is a tenth of a second away.
        """
        updates = message.get("updates")
        for update in updates if isinstance(updates, list) else []:
            raw = update.get("frame") if isinstance(update, dict) else None
            if not isinstance(raw, dict) or "data" not in raw:
                continue
            try:
                frame = Frame.from_state_update(raw)
            except (ValueError, KeyError, TypeError):
                continue
            if frame.display.name is types.DisplayName.FRONT:
                self.show(frame)

    def show(self, frame: Frame | None) -> None:
        if frame != self.frame:
            self.frame = frame
            self.version += 1

    def show_screen(self, data: bytes) -> None:
        """
        Take the bytes `GET /api/screen` answers with, for the moment before
        the stream has sent a frame of its own.
        """
        try:
            self.show(Frame.from_screen(data, "front"))
        except ValueError:
            pass

    def clear(self) -> None:
        self.show(None)
