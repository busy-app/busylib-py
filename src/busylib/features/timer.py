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
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from .. import types

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
