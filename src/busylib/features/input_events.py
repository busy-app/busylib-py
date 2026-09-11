"""
What the bar's buttons, selector and wheel report on the state stream.

The stream carries physical input alongside everything else, as protobuf
one-of messages that arrive decoded into nested dictionaries. Reading them
means knowing the shapes - `button_event`, `switch_event`, `encoder_event` -
and the firmware's SHOUTING enum names, which is exactly the knowledge a
consumer should not have to hold.

`input_events()` turns one state message into the events it carried, so a
caller can react to a press rather than to a dictionary.

Note that the bar reports the selector only when it moves: nothing answers
"where is it now", so its position is unknown until the first move after a
consumer starts listening.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

Button = Literal["ok", "back", "start"]
ButtonAction = Literal["press", "release"]
SelectorPosition = Literal["busy", "custom", "off", "apps", "settings"]

_BUTTONS: dict[str, Button] = {"OK": "ok", "BACK": "back", "START": "start"}
_ACTIONS: dict[str, ButtonAction] = {"PRESS": "press", "RELEASE": "release"}
_POSITIONS: dict[str, SelectorPosition] = {
    "BUSY": "busy",
    "CUSTOM": "custom",
    "OFF": "off",
    "APPS": "apps",
    "SETTINGS": "settings",
}


@dataclass(frozen=True)
class ButtonEvent:
    """
    One of the three buttons went down or came back up.

    Both halves are reported, so a consumer can tell a long press from a
    short one; most only care about `press`.
    """

    button: Button
    action: ButtonAction

    @property
    def is_press(self) -> bool:
        return self.action == "press"


@dataclass(frozen=True)
class SelectorEvent:
    """
    The selector was moved to a position.

    `off` is the bar's do-not-disturb rather than a power state.
    """

    position: SelectorPosition


@dataclass(frozen=True)
class EncoderEvent:
    """
    The wheel was turned, by `delta` steps: positive one way, negative the
    other.
    """

    delta: int


InputEvent: TypeAlias = ButtonEvent | SelectorEvent | EncoderEvent


def _event(payload: Mapping[str, object]) -> InputEvent | None:
    """
    Read one `input` update, or None if it is not one this version knows.
    """
    button = payload.get("button_event")
    if isinstance(button, Mapping):
        # proto3 omits an enum holding its first value, and OK and PRESS are
        # both first - so an absent name means that one rather than nothing.
        name = _BUTTONS.get(str(button.get("button", "OK")))
        action = _ACTIONS.get(str(button.get("action", "PRESS")))
        if name is not None and action is not None:
            return ButtonEvent(button=name, action=action)
        return None

    switch = payload.get("switch_event")
    if isinstance(switch, Mapping):
        position = _POSITIONS.get(str(switch.get("position", "BUSY")))
        return None if position is None else SelectorEvent(position=position)

    encoder = payload.get("encoder_event")
    if isinstance(encoder, Mapping):
        delta = encoder.get("delta", 0)
        return EncoderEvent(delta=int(delta) if isinstance(delta, (int, float)) else 0)

    return None


def input_events(state_message: Mapping[str, object]) -> list[InputEvent]:
    """
    Every input event one state message carried, in the order it carried them.

    A message with no input in it gives an empty list, which is most of
    them: the stream is dominated by screen frames.
    """
    updates = state_message.get("updates")
    if not isinstance(updates, Sequence) or isinstance(updates, (str, bytes)):
        return []

    events: list[InputEvent] = []
    for update in updates:
        if not isinstance(update, Mapping):
            continue
        payload = update.get("input")
        if not isinstance(payload, Mapping):
            continue
        event = _event(payload)
        if event is not None:
            events.append(event)
    return events
