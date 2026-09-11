"""
Working out what a timer is doing right now.

The bar does not run a clock you can read. `GET /api/busy/snapshot` returns
the **last snapshot that was applied**, verbatim, together with the moment it
was applied - verified on firmware 27.7.0, where a snapshot with three
seconds left still reported three seconds left, and the same timestamp,
eleven seconds later. This is deliberate: it is how the apps keep a timer in
step, the freshest snapshot wins, and each client works out the rest.

So reading a snapshot tells you nothing on its own. This module does the
arithmetic every consumer would otherwise repeat: advance the snapshot by
the time that has passed and say what phase the timer is in.

Changing a timer works the same way round: there is no "pause" endpoint,
only a snapshot to write, and the device takes the freshest one as the
truth. The helpers here write the snapshot each change needs - which
includes reading the card first, because the device rejects a snapshot
that disagrees with the card it names.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Protocol

from .. import exceptions, types

TimerMode = Literal["not_started", "infinite", "simple", "interval"]
TimerPhase = Literal["work", "rest"]


@dataclass(frozen=True)
class TimerState:
    """
    What the timer is doing at one moment.

    `phase` is `None` only once a session has finished, where no phase
    applies any more.
    """

    mode: TimerMode
    is_paused: bool
    phase: TimerPhase | None = None
    interval: int | None = None
    time_left_ms: int | None = None
    is_finished: bool | None = None
    elapsed_ms: int = 0

    @property
    def is_running(self) -> bool:
        """
        Whether a session is under way, paused or not.
        """
        return self.mode != "not_started" and not self.is_finished


def phase_of(interval: int) -> TimerPhase:
    """
    Name the phase an interval index belongs to.

    `current_interval` is the firmware's own interval index, sent raw: it
    starts at 0 for the first work period and rises by one at every change
    of phase, so even indices are work and odd ones rest. Comparing the
    interval's length against the configured durations would usually work
    too, but not when work and rest are set equal - the index has no such
    gap.
    """
    return "work" if interval % 2 == 0 else "rest"


def _last_index(settings: types.BusySnapshotIntervalSettings) -> int:
    """
    The index a session ends at, and never occupies.

    Leaving a work period the firmware moves to rest only while the next
    index is below `cycles_count * 2 - 1`, and goes idle otherwise - so
    three cycles run work, rest, work, rest, work and stop, with no rest
    after the final work.
    """
    return settings.interval_work_cycles_count * 2 - 1


def _duration_of(interval: int, settings: types.BusySnapshotIntervalSettings) -> int:
    """
    How long the interval at this index runs for.
    """
    if phase_of(interval) == "work":
        return settings.interval_work_ms
    return settings.interval_rest_ms


def timer_state(
    snapshot: types.BusySnapshot,
    *,
    now_ms: int | None = None,
) -> TimerState:
    """
    Advance a snapshot to `now_ms` and report the timer's state.

    `now_ms` defaults to the current wall clock. A paused snapshot is
    returned as it stands, since paused time does not pass.

    Everything is derived from the interval index rather than from interval
    lengths, so a session configured with equal work and rest is no harder
    to read than any other: the index says which phase it is, and where the
    session ends.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    elapsed = max(0, now - snapshot.snapshot_timestamp_ms)
    inner = snapshot.snapshot

    if isinstance(inner, types.BusySnapshotNotStarted):
        return TimerState(mode="not_started", is_paused=False, is_finished=False)

    if isinstance(inner, types.BusySnapshotInfinite):
        # Open-ended: there is no remaining time to report.
        return TimerState(
            mode="infinite",
            is_paused=inner.is_paused,
            phase="work",
            is_finished=False,
            elapsed_ms=0 if inner.is_paused else elapsed,
        )

    if isinstance(inner, types.BusySnapshotSimple):
        if inner.is_paused:
            return TimerState(
                mode="simple",
                is_paused=True,
                time_left_ms=inner.time_left_ms,
                is_finished=False,
            )
        left = inner.time_left_ms - elapsed
        return TimerState(
            mode="simple",
            is_paused=False,
            time_left_ms=max(0, left),
            is_finished=left <= 0,
            elapsed_ms=elapsed,
        )

    settings = inner.interval_settings
    interval = inner.current_interval

    if inner.is_paused:
        return TimerState(
            mode="interval",
            is_paused=True,
            phase=phase_of(interval),
            interval=interval,
            time_left_ms=inner.current_interval_time_left_ms,
            is_finished=False,
        )

    last = _last_index(settings)
    left = inner.current_interval_time_left_ms - elapsed

    # Walk forward over the boundaries the elapsed time crossed. Each new
    # interval lasts as long as its own phase, and reaching `last` is the
    # session ending rather than another interval starting.
    while left <= 0:
        interval += 1
        if interval >= last:
            return TimerState(
                mode="interval",
                is_paused=False,
                phase=None,
                interval=last,
                time_left_ms=0,
                is_finished=True,
                elapsed_ms=elapsed,
            )
        duration = _duration_of(interval, settings)
        if duration <= 0:
            # A zero-length phase would never end, so stop rather than spin.
            break
        left += duration

    return TimerState(
        mode="interval",
        is_paused=False,
        phase=phase_of(interval),
        interval=interval,
        time_left_ms=max(0, left),
        is_finished=False,
        elapsed_ms=elapsed,
    )


class TimerNotRunningError(exceptions.BusyBarError):
    """
    Raised for a change that only makes sense while a session is running.

    Pausing, resuming, moving to the next phase and setting the session's
    theme all rewrite the running session. With nothing running there is
    nothing to rewrite, and writing a session to make the change possible
    would start one nobody asked for.
    """


# Where the bar keeps the themes it can show, one directory each.
THEMES_PATH = "/ext/apps_assets/busy/themes"

# The theme every bar has, which has no directory of its own.
DEFAULT_THEME = "busy"


class ThemeCatalogueClient(Protocol):
    """
    What `themes()` needs: one call, so a caller can pass anything.
    """

    async def storage_list(self, path: str) -> types.StorageList: ...


class TimerClient(Protocol):
    """
    What these helpers need from a client.

    Deliberately three methods rather than the whole client, so a caller
    can pass anything that speaks them - including a test double.
    """

    async def busy_snapshot(self) -> types.BusySnapshot: ...

    async def busy_snapshot_set(
        self, snapshot: types.BusySnapshot
    ) -> types.SuccessResponse: ...

    async def busy_profile(self, slot: types.BusyProfileSlot) -> types.BusyProfile: ...

    async def busy_profile_set(
        self, slot: types.BusyProfileSlot, profile: types.BusyProfile
    ) -> types.SuccessResponse: ...


async def _apply(
    client: TimerClient,
    variant: types.BusySnapshotVariant,
    *,
    now_ms: int | None = None,
) -> None:
    """
    Send one snapshot as the newest one.

    The device takes the freshest snapshot as the truth, so the timestamp
    is the moment of writing rather than anything carried over from the
    snapshot being replaced.
    """
    stamp = int(time.time() * 1000) if now_ms is None else now_ms
    await client.busy_snapshot_set(
        types.BusySnapshot(snapshot=variant, snapshot_timestamp_ms=stamp)
    )


async def start(
    client: TimerClient,
    slot: types.BusyProfileSlot = "busy",
    *,
    theme: str | None = None,
    now_ms: int | None = None,
) -> None:
    """
    Start the session one of the bar's two cards describes.

    A session is not started by asking for a mode: the mode comes from the
    card. The device rejects a snapshot that disagrees with the card it
    names - `400 Failed to parse snapshot` - so the card is read first and
    the snapshot built from its own settings. To start a countdown of a
    different length, write the card first.

    `theme` overrides the card's theme for this session only; the card
    keeps its own, which is what the bar returns to when the session ends.
    """
    profile = await client.busy_profile(slot)
    settings = profile.busy_bar_settings
    if theme is not None:
        settings = settings.model_copy(update={"theme": theme})

    timer = profile.timer_settings
    variant: types.BusySnapshotVariant
    if isinstance(timer, types.BusyTimerInfiniteSettings):
        variant = types.BusySnapshotInfinite(
            type="INFINITE",
            card_id=profile.id,
            is_paused=False,
            busy_bar_settings=settings,
        )
    elif isinstance(timer, types.BusyTimerSimpleSettings):
        variant = types.BusySnapshotSimple(
            type="SIMPLE",
            card_id=profile.id,
            time_left_ms=timer.total_time_ms,
            is_paused=False,
            busy_bar_settings=settings,
        )
    else:
        variant = types.BusySnapshotInterval(
            type="INTERVAL",
            card_id=profile.id,
            current_interval=0,
            current_interval_time_total_ms=timer.interval_work_ms,
            current_interval_time_left_ms=timer.interval_work_ms,
            is_paused=False,
            interval_settings=timer,
            busy_bar_settings=settings,
        )
    await _apply(client, variant, now_ms=now_ms)


async def stop(client: TimerClient, *, now_ms: int | None = None) -> None:
    """
    End the session, leaving the bar with nothing running.

    This is not the selector's `off` position, which is the bar's
    do-not-disturb: it is the session going back to not started.
    """
    live = await client.busy_snapshot()
    await _apply(
        client,
        types.BusySnapshotNotStarted(
            type="NOT_STARTED",
            busy_bar_settings=live.snapshot.busy_bar_settings,
        ),
        now_ms=now_ms,
    )


async def set_paused(
    client: TimerClient, paused: bool, *, now_ms: int | None = None
) -> None:
    """
    Pause or resume the running session.

    Pausing writes back how much time is actually left, not the figure the
    stored snapshot carries: that one was true when it was written, and
    resuming from it would hand back the time the session already spent.
    """
    live = await client.busy_snapshot()
    variant = live.snapshot
    if isinstance(variant, types.BusySnapshotNotStarted):
        raise TimerNotRunningError(
            "no session is running, so there is nothing to pause"
        )

    update: dict[str, object] = {"is_paused": paused}
    if paused:
        state = timer_state(live, now_ms=now_ms)
        if state.time_left_ms is not None:
            field = (
                "time_left_ms"
                if isinstance(variant, types.BusySnapshotSimple)
                else "current_interval_time_left_ms"
            )
            if field != "time_left_ms" and isinstance(
                variant, types.BusySnapshotInterval
            ):
                update["current_interval"] = state.interval
                update["current_interval_time_total_ms"] = _duration_of(
                    state.interval or 0, variant.interval_settings
                )
            update[field] = state.time_left_ms
    await _apply(client, variant.model_copy(update=update), now_ms=now_ms)


async def next_phase(client: TimerClient, *, now_ms: int | None = None) -> None:
    """
    Move an interval session on to its next phase.

    Work becomes rest and rest becomes the next work, at that phase's full
    length. Past the last interval the session is over, so it is stopped
    rather than wrapped around.
    """
    live = await client.busy_snapshot()
    variant = live.snapshot
    if not isinstance(variant, types.BusySnapshotInterval):
        raise TimerNotRunningError(
            "only an interval session has phases to move between"
        )

    state = timer_state(live, now_ms=now_ms)
    following = (state.interval or 0) + 1
    if following > _last_index(variant.interval_settings):
        await stop(client, now_ms=now_ms)
        return

    duration = _duration_of(following, variant.interval_settings)
    await _apply(
        client,
        variant.model_copy(
            update={
                "current_interval": following,
                "current_interval_time_total_ms": duration,
                "current_interval_time_left_ms": duration,
                "is_paused": False,
            }
        ),
        now_ms=now_ms,
    )


async def set_session_theme(
    client: TimerClient, theme: str, *, now_ms: int | None = None
) -> None:
    """
    Change the theme the running session is showing.

    This lasts as long as the session: the card keeps its own theme, and
    the bar shows that one again next time it starts. Confirmed on
    hardware - a session switched to `dnd` came back as the card's `busy`
    once stopped.
    """
    live = await client.busy_snapshot()
    variant = live.snapshot
    if isinstance(variant, types.BusySnapshotNotStarted):
        raise TimerNotRunningError(
            "no session is running, so there is no session theme to change"
        )
    settings = variant.busy_bar_settings.model_copy(update={"theme": theme})
    await _apply(
        client,
        variant.model_copy(update={"busy_bar_settings": settings}),
        now_ms=now_ms,
    )


async def set_card_theme(
    client: TimerClient,
    slot: types.BusyProfileSlot,
    theme: str,
    *,
    now_ms: int | None = None,
) -> None:
    """
    Change the theme one of the bar's cards starts with.

    Unlike `set_session_theme` this outlasts the session, and it does not
    touch what is on screen now - a session already running keeps the
    theme it started with.

    The profile is stamped with the moment of writing, for the same reason
    a snapshot is: the device keeps whichever copy is newer and silently
    discards the rest. A card read back and written unchanged carries the
    stored timestamp, which is not newer - and a bar fresh from the
    factory reports `profile_timestamp_ms: 0`, so the write is dropped
    while still answering `{"result": "OK"}`. Confirmed on firmware r971.
    """
    profile = await client.busy_profile(slot)
    settings = profile.busy_bar_settings.model_copy(update={"theme": theme})
    stamp = int(time.time() * 1000) if now_ms is None else now_ms
    await client.busy_profile_set(
        slot,
        profile.model_copy(
            update={"busy_bar_settings": settings, "profile_timestamp_ms": stamp}
        ),
    )


async def themes(client: ThemeCatalogueClient) -> list[str]:
    """
    Which themes this bar can show.

    A theme is a free string on the wire, and the set is not an enum
    anyone can write down: it is whatever the firmware ships, and it grows
    between releases. So it is read from the bar - the themes are one
    directory each - rather than copied into consumers where it goes stale,
    or discovered by sending a wrong one and reading the result.

    The theme setters do not check against this list, because that would
    cost a directory listing on every write. Ask for it once, offer it to
    whoever is choosing, and pass what they chose.
    """
    listing = await client.storage_list(THEMES_PATH)
    names = {
        entry.name
        for entry in (listing.list or [])
        # One directory per theme; anything else in there is not a theme.
        if entry.name and entry.type == "dir"
    }
    names.add(DEFAULT_THEME)
    return sorted(names)
