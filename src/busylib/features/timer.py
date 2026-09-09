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

TimerKind = Literal["not_started", "infinite", "simple", "interval"]
TimerPhase = Literal["work", "rest"]


@dataclass(frozen=True)
class TimerState:
    """
    What the timer is doing at one moment.

    `phase` and `is_finished` are `None` when the device's data does not
    settle them, rather than being guessed - see `timer_state`.
    """

    kind: TimerKind
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
        return self.kind != "not_started" and not self.is_finished


def _phase_of(
    total_ms: int, settings: types.BusySnapshotIntervalSettings
) -> TimerPhase | None:
    """
    Name the phase an interval of this length belongs to.

    The device does not report the phase, only how long the current interval
    runs for, so it is recovered by comparing that against the work and rest
    durations. When the two are configured equal - 25 and 25, say - the
    comparison cannot tell them apart, and `None` says so instead of picking
    one.
    """
    work, rest = settings.interval_work_ms, settings.interval_rest_ms
    if work == rest:
        return None
    if total_ms == work:
        return "work"
    if total_ms == rest:
        return "rest"
    return None


def _other(phase: TimerPhase) -> TimerPhase:
    return "rest" if phase == "work" else "work"


def timer_state(
    snapshot: types.BusySnapshot,
    *,
    now_ms: int | None = None,
) -> TimerState:
    """
    Advance a snapshot to `now_ms` and report the timer's state.

    `now_ms` defaults to the current wall clock. A paused snapshot is
    returned as it stands, since paused time does not pass.

    Two things are reported as `None` rather than guessed:

    `phase` for an interval timer whose work and rest are configured to the
    same length - the device only reports the current interval's duration,
    so the two are then indistinguishable.

    `is_finished` for an interval timer at all. Whether a session has run its
    course depends on how many work cycles came before the snapshot, and the
    device neither counts them nor defines how a client numbers intervals -
    it just stores what it was handed. A consumer that needs this has to get
    it from whoever writes the snapshots.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    elapsed = max(0, now - snapshot.snapshot_timestamp_ms)
    inner = snapshot.snapshot

    if isinstance(inner, types.BusySnapshotNotStarted):
        return TimerState(kind="not_started", is_paused=False, is_finished=False)

    if inner.is_paused:
        # Nothing moves while paused, so the snapshot is already the answer.
        if isinstance(inner, types.BusySnapshotInfinite):
            return TimerState(kind="infinite", is_paused=True, phase="work")
        if isinstance(inner, types.BusySnapshotSimple):
            return TimerState(
                kind="simple",
                is_paused=True,
                time_left_ms=inner.time_left_ms,
                is_finished=False,
            )
        return TimerState(
            kind="interval",
            is_paused=True,
            phase=_phase_of(
                inner.current_interval_time_total_ms, inner.interval_settings
            ),
            interval=inner.current_interval,
            time_left_ms=inner.current_interval_time_left_ms,
        )

    if isinstance(inner, types.BusySnapshotInfinite):
        # Open-ended: there is no remaining time to report.
        return TimerState(
            kind="infinite",
            is_paused=False,
            phase="work",
            is_finished=False,
            elapsed_ms=elapsed,
        )

    if isinstance(inner, types.BusySnapshotSimple):
        left = inner.time_left_ms - elapsed
        return TimerState(
            kind="simple",
            is_paused=False,
            time_left_ms=max(0, left),
            is_finished=left <= 0,
            elapsed_ms=elapsed,
        )

    settings = inner.interval_settings
    phase = _phase_of(inner.current_interval_time_total_ms, settings)
    interval = inner.current_interval
    left = inner.current_interval_time_left_ms - elapsed

    # Walk forward over any boundaries the elapsed time crossed. Phases
    # alternate, so each new interval lasts as long as its own phase.
    while left <= 0:
        if phase is None:
            # Without a phase the next interval's length is unknown, so the
            # walk cannot continue; report the boundary it stopped at.
            return TimerState(
                kind="interval",
                is_paused=False,
                phase=None,
                interval=interval,
                time_left_ms=0,
                elapsed_ms=elapsed,
            )
        phase = _other(phase)
        duration = (
            settings.interval_work_ms if phase == "work" else settings.interval_rest_ms
        )
        if duration <= 0:
            break
        interval += 1
        left += duration

    return TimerState(
        kind="interval",
        is_paused=False,
        phase=phase,
        interval=interval,
        time_left_ms=max(0, left),
        elapsed_ms=elapsed,
    )
