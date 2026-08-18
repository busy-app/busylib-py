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

# proto3 omits fields holding a default value, so the first entry of each enum
# arrives as an absent key: OK is button 0 and PRESS is action 0, which makes
# "OK pressed" indistinguishable from an empty message unless the defaults are
# filled in. Everything below reads events through _button, never raw.
DEFAULT_BUTTON = "OK"
DEFAULT_ACTION = "PRESS"


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


@pytest.mark.manual
async def test_physical_buttons_reach_the_stream(local_only, abar) -> None:
    """
    A human presses buttons on the bar and the stream reports them.

    Forwarded input travelling the same channel does not prove the hardware
    does, which is why this exists separately. Run it with output shown:

        uv run pytest -m "integration and manual" -s

    Then press OK, BACK and START on the bar within the timeout.
    """
    wanted = {"OK", "BACK", "START"}
    print(
        f"\nPress OK, BACK and START on the bar ({MANUAL_TIMEOUT_SECONDS:.0f}s)...",
        flush=True,
    )

    pressed: set[str] = set()

    def enough(updates: list[dict]) -> bool:
        for update in updates[-1:]:
            found = _button(update)
            if found is not None and found[1] == "PRESS":
                if found[0] not in pressed:
                    pressed.add(found[0])
                    print(f"  saw {found[0]}", flush=True)
        return wanted.issubset(pressed)

    await _collect(abar, MANUAL_TIMEOUT_SECONDS, stop_when=enough)

    assert wanted.issubset(pressed), (
        f"missing {sorted(wanted - pressed)}; got {sorted(pressed)}"
    )
