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
from collections.abc import Sequence
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


# Where the bar keeps the themes it has assets for, one directory each.
THEMES_PATH = "/ext/apps_assets/busy/themes"

# The shortest phase the device will accept. Anything under it is stored
# nowhere: the write answers {"result": "OK"} and the card keeps what it
# had. Found by bisection on firmware r971 - four minutes is ignored, five
# is kept, six and seven are kept, so it is a floor rather than a step -
# and documented nowhere, the bar's own OpenAPI even showing 120000 as its
# example.
MINIMUM_PHASE_MS = 5 * 60 * 1000

# What a card is given when it changes to a kind of timer it was not
# running before. There is nothing to carry over in that case - an endless
# card has no lengths at all - so these are the values a fresh pomodoro or
# countdown starts from, and a caller can pass its own alongside.
DEFAULT_WORK_MS = 25 * 60 * 1000
DEFAULT_REST_MS = 5 * 60 * 1000
DEFAULT_CYCLES = 4
DEFAULT_TOTAL_MS = 25 * 60 * 1000

TimerKind = Literal["endless", "countdown", "pomodoro"]

# The firmware's names for them, which the wire uses.
_KIND_TO_TYPE: dict[TimerKind, str] = {
    "endless": "INFINITE",
    "countdown": "SIMPLE",
    "pomodoro": "INTERVAL",
}
_TYPE_TO_KIND: dict[str, TimerKind] = {
    "INFINITE": "endless",
    "SIMPLE": "countdown",
    "INTERVAL": "pomodoro",
}


def kind_of(settings: types.BusyTimerSettings) -> TimerKind:
    """
    Which kind of timer a card holds, in this package's words.
    """
    return _TYPE_TO_KIND[settings.type]


class UnknownThemeError(exceptions.BusyBarError):
    """
    Raised for a theme this bar does not have.

    The device does not raise it: a profile naming a theme that does not
    exist is stored and read back happily, and only the bar's own screen
    shows that something is wrong. So the check has to happen here, or a
    typo leaves a card pointing at nothing with every layer reporting
    success.
    """

    def __init__(self, theme: str, available: Sequence[str]) -> None:
        self.theme = theme
        self.available = list(available)
        super().__init__(
            f"this bar has no theme {theme!r}; it has: {', '.join(self.available)}"
        )


class PhaseTooShortError(exceptions.BusyBarError):
    """
    Raised for a phase the device would silently refuse to store.

    It does not reject them: a card written with a two-minute work phase
    comes back with the phase it had before, and every layer reports
    success. So a caller that is not told here finds out by watching a bar
    run the wrong timer.
    """

    def __init__(self, field: str, given_ms: int) -> None:
        self.field = field
        self.given_ms = given_ms
        super().__init__(
            f"{field} is {given_ms / 60000:g} minutes; the bar silently ignores "
            f"anything under {MINIMUM_PHASE_MS // 60000} and keeps what it had"
        )


class ThemeCatalogueClient(Protocol):
    """
    What `themes()` needs, which is less than the whole client.
    """

    async def storage_list(self, path: str) -> types.StorageList: ...

    async def busy_profile(self, slot: types.BusyProfileSlot) -> types.BusyProfile: ...


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

    async def storage_list(self, path: str) -> types.StorageList: ...


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
    client: TimerClient,
    theme: str,
    *,
    known: Sequence[str] | None = None,
    now_ms: int | None = None,
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
    await _checked(client, theme, known)
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
    known: Sequence[str] | None = None,
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
    await _checked(client, theme, known)
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

    Not a fixed set and not an enum: themes are assets, so one bar has
    what the firmware shipped, another has one the owner uploaded, and a
    third is missing one the owner deleted. It is read from the bar rather
    than written down anywhere that would go stale.

    Two sources, because neither alone is the answer. The assets are one
    directory each under `THEMES_PATH`. And whichever themes the bar's own
    cards are set to are real by definition, which is how the firmware's
    built-in default gets in - it has no directory, so a listing alone
    would report a bar cannot show the theme it is showing right now.
    """
    listing = await client.storage_list(THEMES_PATH)
    names = {
        entry.name
        for entry in (listing.list or [])
        # One directory per theme; anything else in there is not a theme.
        if entry.name and entry.type == "dir"
    }
    for slot in ("busy", "custom"):
        profile = await client.busy_profile(slot)
        if profile.busy_bar_settings.theme:
            names.add(profile.busy_bar_settings.theme)
    return sorted(names)


async def _checked(
    client: ThemeCatalogueClient, theme: str, known: Sequence[str] | None
) -> None:
    """
    Refuse a theme this bar does not have, since the device will not.
    """
    available = list(known) if known is not None else await themes(client)
    if theme not in available:
        raise UnknownThemeError(theme, available)


def _phase(field: str, value: int | None) -> int | None:
    """
    Check one duration, since the device checks none of them out loud.
    """
    if value is not None and value < MINIMUM_PHASE_MS:
        raise PhaseTooShortError(field, value)
    return value


def _settings_for(
    kind: TimerKind,
    *,
    work_ms: int | None,
    rest_ms: int | None,
    cycles: int | None,
    total_ms: int | None,
    autostart: bool,
) -> types.BusyTimerSettings:
    """
    Build a fresh timer of one kind, for a card changing to it.
    """
    if kind == "endless":
        return types.BusyTimerInfiniteSettings(type="INFINITE")
    if kind == "countdown":
        return types.BusyTimerSimpleSettings(
            type="SIMPLE",
            total_time_ms=_phase("total_ms", total_ms) or DEFAULT_TOTAL_MS,
        )
    return types.BusySnapshotIntervalSettings(
        type="INTERVAL",
        interval_work_ms=_phase("work_ms", work_ms) or DEFAULT_WORK_MS,
        interval_rest_ms=_phase("rest_ms", rest_ms) or DEFAULT_REST_MS,
        interval_work_cycles_count=cycles or DEFAULT_CYCLES,
        is_autostart_enabled=autostart,
    )


async def configure(
    client: TimerClient,
    slot: types.BusyProfileSlot = "busy",
    *,
    kind: TimerKind | None = None,
    duration_ms: int | None = None,
    work_ms: int | None = None,
    rest_ms: int | None = None,
    cycles: int | None = None,
    total_ms: int | None = None,
    theme: str | None = None,
    known_themes: Sequence[str] | None = None,
    now_ms: int | None = None,
) -> types.BusyProfile:
    """
    Change one of the bar's two cards, leaving the rest of it alone.

    This is how a session gets its own length. The device refuses a
    snapshot whose settings disagree with the card it names, so there is no
    way to run a timer for twenty-five minutes without the card saying
    twenty-five minutes - which is why this exists and why the change
    outlasts the session. The bar and the phone app see it too; that is the
    same thing they do to each other.

    Only what is given is changed. `work_ms`, `rest_ms` and `cycles` apply
    to an interval card, `total_ms` to a countdown; giving one the card
    cannot use is an error rather than a silent no-op, since the device
    would treat it as one.

    Returns the profile as written, so a caller can see what the card now
    holds.
    """
    profile = await client.busy_profile(slot)
    settings = profile.timer_settings

    # "How long should it run" is one question with two answers depending
    # on the card, and a caller starting a session should not have to know
    # which: a countdown has a total, a pomodoro has a work phase, and a
    # card that runs endlessly has neither.
    if duration_ms is not None:
        wanted = kind or kind_of(settings)
        if wanted == "endless":
            raise ValueError(
                f"the {slot} card runs without a clock; it has no length to set"
            )
        if wanted == "countdown":
            total_ms = duration_ms if total_ms is None else total_ms
        else:
            work_ms = duration_ms if work_ms is None else work_ms

    if theme is not None:
        await _checked(client, theme, known_themes)

    changed: dict[str, object] = {}
    if kind is not None and kind != kind_of(settings):
        # A different kind of timer is a different object, not an edit: an
        # endless card has no lengths to keep, and the device stores
        # whichever one it is given. Verified on firmware r971, where a
        # card went endless -> pomodoro -> countdown -> endless and kept
        # each one.
        changed["timer_settings"] = _settings_for(
            kind,
            work_ms=work_ms,
            rest_ms=rest_ms,
            cycles=cycles,
            total_ms=total_ms,
            autostart=getattr(settings, "is_autostart_enabled", False),
        )
        work_ms = rest_ms = cycles = total_ms = None
        settings = changed["timer_settings"]  # type: ignore[assignment]

    updates: dict[str, object] = {}
    if isinstance(settings, types.BusySnapshotIntervalSettings):
        if total_ms is not None:
            raise ValueError(f"the {slot} card runs intervals; use work_ms and rest_ms")
        if work_ms is not None:
            updates["interval_work_ms"] = _phase("work_ms", work_ms)
        if rest_ms is not None:
            updates["interval_rest_ms"] = _phase("rest_ms", rest_ms)
        if cycles is not None:
            updates["interval_work_cycles_count"] = cycles
    elif isinstance(settings, types.BusyTimerSimpleSettings):
        if work_ms is not None or rest_ms is not None or cycles is not None:
            raise ValueError(f"the {slot} card runs a countdown; use total_ms")
        if total_ms is not None:
            updates["total_time_ms"] = _phase("total_ms", total_ms)
    elif work_ms is not None or rest_ms is not None or total_ms is not None:
        raise ValueError(f"the {slot} card runs without a clock; it has no length")

    if updates:
        changed["timer_settings"] = settings.model_copy(update=updates)
    if theme is not None:
        changed["busy_bar_settings"] = profile.busy_bar_settings.model_copy(
            update={"theme": theme}
        )
    if not changed:
        return profile

    # Stamped, or the device keeps the copy it has and says OK anyway.
    changed["profile_timestamp_ms"] = (
        int(time.time() * 1000) if now_ms is None else now_ms
    )
    written = profile.model_copy(update=changed)
    await client.busy_profile_set(slot, written)
    return written
