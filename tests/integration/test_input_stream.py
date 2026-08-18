"""
What the status stream reports, and whether the hardware reaches it.

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

# The client fills the protobuf defaults that a plain conversion drops, so a
# press of OK arrives complete rather than as an empty payload (#77). These
# helpers read the fields directly rather than with a fallback, which makes
# them fail if that normalization is ever lost.


def _button(event: dict) -> tuple[str, str] | None:
    """
    Return (button, action) from an update, or None if it is not a button.
    """
    payload = event.get("input", {}).get("button_event")
    if payload is None:
        return None
    return (payload["button"], payload["action"])


def _switch(event: dict) -> str | None:
    """
    Return the switch position from an update, or None if it is not a switch.
    """
    payload = event.get("input", {}).get("switch_event")
    if payload is None:
        return None
    return payload["position"]


def _encoder(event: dict) -> int | None:
    """
    Return the encoder delta from an update, or None if it is not an encoder.

    The firmware sends +1 and -1 and never 0, so a missing delta would mean a
    contract change rather than "no movement".
    """
    payload = event.get("input", {}).get("encoder_event")
    if payload is None:
        return None
    return payload["delta"]


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


async def _forward_and_watch(abar, keys, extract) -> list:
    """
    Forward input while listening, and return whatever `extract` recognised.
    """
    seen: list = []

    async def listen() -> None:
        async for message in abar.stream_status_ws():
            if not isinstance(message, dict):
                continue
            for update in message.get("updates", []):
                found = extract(update)
                if found is not None:
                    seen.append(found)

    listener = asyncio.create_task(listen())
    await asyncio.sleep(STREAM_SETTLE_SECONDS)
    try:
        for key in keys:
            await abar.input(types.InputKey(key))
            await asyncio.sleep(0.35)
        await asyncio.sleep(1.0)
    finally:
        listener.cancel()
    return seen


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


async def test_forwarded_buttons_come_back_on_the_stream(local_only, abar) -> None:
    """
    Every forwarded button appears as a press and a release.

    This is the automatic half of the key-press check: it proves the stream
    carries input at all, so a failure in the manual test points at the
    hardware path rather than at this client.
    """
    expected = ["ok", "back", "start"]

    seen = await _forward_and_watch(abar, expected, _button)

    for key in expected:
        name = key.upper()
        assert (name, "PRESS") in seen, f"no press for {name}, saw {seen}"
        assert (name, "RELEASE") in seen, f"no release for {name}, saw {seen}"


async def test_forwarded_wheel_movement_comes_back(local_only, abar) -> None:
    """
    The stream carries wheel movement, not only buttons.

    Only buttons were checked at first, which made scrolling look as though it
    were never reported. It is, as an encoder delta of +1 or -1.

    Switch positions are deliberately not forwarded here. They change the
    bar's operating mode - sending `off` stops a running Busy session, and a
    session owns the display, so a draw afterwards is refused with `409 Not
    drawn due to low priority`. That cost three unexplained failures elsewhere
    in this suite. Switch decoding is covered without a device in
    tests/busylib/client/test_state_decoding.py, and the physical switch by the
    manual test below.
    """
    deltas = await _forward_and_watch(abar, ["up", "down"], _encoder)

    assert 1 in deltas, f"no forward wheel movement, saw {deltas}"
    assert -1 in deltas, f"no backward wheel movement, saw {deltas}"


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
