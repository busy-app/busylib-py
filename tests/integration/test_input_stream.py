"""
What the status stream reports, and whether physical buttons reach it.

`/api/status/ws` is a local endpoint by design, so none of this runs through
the cloud. The synthetic half is automatic: input forwarded over HTTP comes
back on the stream, which proves the whole path without anyone touching the
bar. The physical half needs a person and is marked `manual`.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from busylib import types

pytestmark = pytest.mark.integration

STREAM_SETTLE_SECONDS = 1.5
STREAM_DRAIN_SECONDS = 2.0
MANUAL_TIMEOUT_SECONDS = float(os.environ.get("BUSYBAR_TEST_MANUAL_TIMEOUT", "30"))

# proto3 omits fields holding a default value, so the first entry of every enum
# arrives as an absent key. That bites three times here: OK is button 0, PRESS
# is action 0, and BUSY is switch position 0, so "OK pressed" and "switched to
# BUSY" both look like an empty message. Nothing below reads a payload raw.
DEFAULT_BUTTON = "OK"
DEFAULT_ACTION = "PRESS"
DEFAULT_SWITCH_POSITION = "BUSY"


def _button(event: dict) -> tuple[str, str] | None:
    """
    Return (button, action) from an update, or None if it is not a button.
    """
    payload = event.get("input", {}).get("button_event")
    if payload is None:
        return None
    return (
        payload.get("button", DEFAULT_BUTTON),
        payload.get("action", DEFAULT_ACTION),
    )


def _switch(event: dict) -> str | None:
    """
    Return the switch position from an update, or None if it is not a switch.
    """
    payload = event.get("input", {}).get("switch_event")
    if payload is None:
        return None
    return payload.get("position", DEFAULT_SWITCH_POSITION)


def _encoder(event: dict) -> int | None:
    """
    Return the encoder delta from an update, or None if it is not an encoder.

    The firmware sends +1 and -1 and never 0, so an absent delta would mean a
    contract change rather than "no movement".
    """
    payload = event.get("input", {}).get("encoder_event")
    if payload is None:
        return None
    return payload.get("delta", 0)


async def _collect(abar, seconds: float, stop_when=None) -> list[dict]:
    """
    Gather stream updates for a while, or until `stop_when` is satisfied.
    """
    updates: list[dict] = []

    async def listen() -> None:
        async for message in abar.stream_status_ws():
            if not isinstance(message, dict):
                continue
            for update in message.get("updates", []):
                updates.append(update)
                if stop_when is not None and stop_when(updates):
                    return

    try:
        await asyncio.wait_for(listen(), timeout=seconds)
    except asyncio.TimeoutError:
        pass
    return updates


async def test_stream_yields_frames(local_only, abar) -> None:
    """
    The stream produces screen frames without being prompted.
    """
    updates = await _collect(
        abar,
        STREAM_DRAIN_SECONDS,
        stop_when=lambda seen: any("frame" in u for u in seen),
    )

    assert any("frame" in u for u in updates), (
        f"no frame updates in {len(updates)} stream messages"
    )


async def test_forwarded_input_comes_back_on_the_stream(local_only, abar) -> None:
    """
    Every forwarded button appears as a press and a release.

    This is the automatic half of the key-press check: it proves the stream
    carries input at all, so a failure in the manual test below points at the
    hardware path rather than at this client.
    """
    expected = [types.InputKey.OK, types.InputKey.BACK, types.InputKey.START]
    seen: list[tuple[str, str]] = []

    async def listen() -> None:
        async for message in abar.stream_status_ws():
            if not isinstance(message, dict):
                continue
            for update in message.get("updates", []):
                pressed = _button(update)
                if pressed is not None:
                    seen.append(pressed)

    listener = asyncio.create_task(listen())
    await asyncio.sleep(STREAM_SETTLE_SECONDS)
    try:
        for key in expected:
            await abar.input(key)
            await asyncio.sleep(0.4)
        await asyncio.sleep(1.0)
    finally:
        listener.cancel()

    for key in expected:
        name = key.value.upper()
        assert (name, "PRESS") in seen, f"no press for {name}, saw {seen}"
        assert (name, "RELEASE") in seen, f"no release for {name}, saw {seen}"


async def test_forwarded_encoder_and_switch_come_back(local_only, abar) -> None:
    """
    The stream carries wheel movement and switch positions too.

    Only buttons were checked at first, which made it look as though scrolling
    and the switch were not reported at all - they were, the test just never
    asked.
    """
    deltas: list[int] = []
    positions: list[str] = []

    async def listen() -> None:
        async for message in abar.stream_status_ws():
            if not isinstance(message, dict):
                continue
            for update in message.get("updates", []):
                delta = _encoder(update)
                if delta is not None:
                    deltas.append(delta)
                position = _switch(update)
                if position is not None:
                    positions.append(position)

    listener = asyncio.create_task(listen())
    await asyncio.sleep(STREAM_SETTLE_SECONDS)
    try:
        for key in ("up", "down", "busy", "custom", "off", "apps", "settings"):
            await abar.input(types.InputKey(key))
            await asyncio.sleep(0.35)
        await asyncio.sleep(1.0)
    finally:
        listener.cancel()

    assert 1 in deltas, f"no forward wheel movement, saw {deltas}"
    assert -1 in deltas, f"no backward wheel movement, saw {deltas}"
    # BUSY is position 0 and so arrives with no field at all; reading it
    # through _switch is what keeps it from vanishing.
    for expected in ("BUSY", "CUSTOM", "OFF", "APPS", "SETTINGS"):
        assert expected in positions, f"no {expected}, saw {positions}"


@pytest.mark.manual
async def test_physical_input_reaches_the_stream(local_only, abar) -> None:
    """
    A human uses the bar and the stream reports every kind of input.

    Forwarded input travelling the same channel does not prove the hardware
    does, which is why this exists separately. Run it with output shown:

        uv run pytest -m "integration and manual" -s

    Then press the buttons, turn the wheel both ways, and move the switch.
    """
    wanted_buttons = {"OK", "BACK", "START"}
    buttons: set[str] = set()
    directions: set[str] = set()
    positions: set[str] = set()

    print(
        f"\nOn the bar, within {MANUAL_TIMEOUT_SECONDS:.0f}s:"
        "\n  press OK, BACK and START"
        "\n  turn the wheel one way and back"
        "\n  move the switch to any other position",
        flush=True,
    )

    def enough(updates: list[dict]) -> bool:
        for update in updates[-1:]:
            found = _button(update)
            if found is not None and found[1] == "PRESS" and found[0] not in buttons:
                buttons.add(found[0])
                print(f"  button {found[0]}", flush=True)

            delta = _encoder(update)
            if delta is not None:
                direction = "forward" if delta > 0 else "backward"
                if direction not in directions:
                    directions.add(direction)
                    print(f"  wheel {direction} (delta {delta})", flush=True)

            position = _switch(update)
            if position is not None and position not in positions:
                positions.add(position)
                print(f"  switch {position}", flush=True)

        return (
            wanted_buttons.issubset(buttons)
            and len(directions) == 2
            and bool(positions)
        )

    await _collect(abar, MANUAL_TIMEOUT_SECONDS, stop_when=enough)

    missing: list[str] = []
    if not wanted_buttons.issubset(buttons):
        missing.append(f"buttons {sorted(wanted_buttons - buttons)}")
    if len(directions) < 2:
        missing.append(f"wheel directions (saw {sorted(directions) or 'none'})")
    if not positions:
        missing.append("any switch movement")

    assert not missing, "; ".join(missing)
