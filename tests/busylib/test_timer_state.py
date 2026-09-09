from __future__ import annotations

import pytest
from pydantic import ValidationError

from busylib import types
from busylib.features import timer_state

SETTINGS = {"theme": "busy", "show_work_phase_only": False, "trigger_smart_home": True}
WORK = 20 * 60 * 1000
REST = 5 * 60 * 1000


def _interval(
    *,
    total: int = WORK,  # kept for realism; the phase comes from the index
    left: int = WORK,
    interval: int = 0,
    paused: bool = False,
    work: int = WORK,
    rest: int = REST,
    ts: int = 1_000_000,
) -> types.BusySnapshot:
    return types.BusySnapshot(
        snapshot=types.BusySnapshotInterval(
            type="INTERVAL",
            card_id="00000000-0000-0000-0000-000000000000",
            current_interval=interval,
            current_interval_time_total_ms=total,
            current_interval_time_left_ms=left,
            is_paused=paused,
            interval_settings=types.BusySnapshotIntervalSettings(
                type="INTERVAL",
                interval_work_ms=work,
                interval_rest_ms=rest,
                interval_work_cycles_count=3,
                is_autostart_enabled=False,
            ),
            busy_bar_settings=types.BusyBarSettings(**SETTINGS),
        ),
        snapshot_timestamp_ms=ts,
    )


def test_a_snapshot_without_settings_is_refused() -> None:
    """
    `busy_bar_settings` is required, so a write cannot omit it.

    The device answers `400 Failed to parse snapshot` for a snapshot that
    leaves it out, which is what made `busy_snapshot_set` unusable while the
    models did not carry the field.
    """
    with pytest.raises(ValidationError, match="busy_bar_settings"):
        types.BusySnapshotNotStarted(type="NOT_STARTED")  # type: ignore[call-arg]


def test_not_started_is_not_running() -> None:
    snapshot = types.BusySnapshot(
        snapshot=types.BusySnapshotNotStarted(
            type="NOT_STARTED", busy_bar_settings=types.BusyBarSettings(**SETTINGS)
        ),
        snapshot_timestamp_ms=1_000_000,
    )

    state = timer_state(snapshot, now_ms=9_999_999)

    assert state.mode == "not_started"
    assert not state.is_running


def test_a_paused_snapshot_is_the_answer_already() -> None:
    """
    Paused time does not pass, however long ago the snapshot was taken.
    """
    state = timer_state(_interval(left=90_000, paused=True), now_ms=1_000_000 + 600_000)

    assert state.is_paused
    assert state.time_left_ms == 90_000
    assert state.phase == "work"
    assert state.is_running


def test_a_simple_timer_counts_down_and_finishes() -> None:
    snapshot = types.BusySnapshot(
        snapshot=types.BusySnapshotSimple(
            type="SIMPLE",
            card_id="00000000-0000-0000-0000-000000000000",
            time_left_ms=60_000,
            is_paused=False,
            busy_bar_settings=types.BusyBarSettings(**SETTINGS),
        ),
        snapshot_timestamp_ms=1_000_000,
    )

    running = timer_state(snapshot, now_ms=1_000_000 + 20_000)
    assert running.time_left_ms == 40_000
    assert running.is_finished is False

    done = timer_state(snapshot, now_ms=1_000_000 + 90_000)
    assert done.time_left_ms == 0
    assert done.is_finished is True
    assert not done.is_running


def test_an_infinite_timer_reports_no_remaining_time() -> None:
    """
    There is nothing to count down to, so `time_left_ms` stays None.
    """
    snapshot = types.BusySnapshot(
        snapshot=types.BusySnapshotInfinite(
            type="INFINITE",
            card_id="00000000-0000-0000-0000-000000000000",
            is_paused=False,
            busy_bar_settings=types.BusyBarSettings(**SETTINGS),
        ),
        snapshot_timestamp_ms=1_000_000,
    )

    state = timer_state(snapshot, now_ms=1_000_000 + 3_600_000)

    assert state.mode == "infinite"
    assert state.phase == "work"
    assert state.time_left_ms is None
    assert state.is_running


def test_an_interval_advances_inside_its_own_phase() -> None:
    state = timer_state(_interval(left=WORK), now_ms=1_000_000 + 60_000)

    assert state.phase == "work"
    assert state.interval == 0
    assert state.time_left_ms == WORK - 60_000


def test_the_phase_comes_from_the_index_not_the_length() -> None:
    """
    Even indices are work, odd ones rest - whatever the durations say.

    `current_interval` is the firmware's own index: it starts at 0 for the
    first work period and rises by one at every change of phase.
    """
    for interval, phase in ((0, "work"), (1, "rest"), (2, "work"), (3, "rest")):
        state = timer_state(_interval(interval=interval, left=60_000), now_ms=1_000_000)
        assert state.phase == phase, interval


def test_equal_work_and_rest_are_read_like_any_other_session() -> None:
    """
    Configuring both to 25 minutes takes nothing away.

    Reading the phase off interval lengths would fail here, which is why it
    is read off the index instead.
    """
    equal = _interval(
        interval=1, total=25 * 60_000, left=60_000, work=25 * 60_000, rest=25 * 60_000
    )

    state = timer_state(equal, now_ms=1_000_000 + 10_000)

    assert state.phase == "rest"
    assert state.time_left_ms == 50_000
    assert state.is_running


def test_crossing_a_boundary_flips_the_phase_and_takes_its_length() -> None:
    """
    The next interval lasts as long as the phase it belongs to.

    Work is 20 minutes here and rest 5, so 30 seconds from the end of work
    lands 30 seconds into rest, with rest's own length behind it.
    """
    state = timer_state(_interval(left=30_000), now_ms=1_000_000 + 60_000)

    assert state.phase == "rest"
    assert state.interval == 1
    assert state.time_left_ms == REST - 30_000


def test_several_boundaries_are_walked() -> None:
    """
    A snapshot left behind a while still lands in the right phase.
    """
    # work@0 has 30s left, then rest(5m)@1, work(20m)@2, rest(5m)@3 ...
    state = timer_state(_interval(left=30_000), now_ms=1_000_000 + 26 * 60_000)

    # 0:30 ends work@0, 5:30 ends rest@1, 25:30 ends work@2 -> rest@3
    assert state.interval == 3
    assert state.phase == "rest"
    assert state.is_finished is False


def test_a_session_ends_after_its_last_work_period() -> None:
    """
    Three cycles run work, rest, work, rest, work and stop.

    The firmware leaves a work period for rest only while the next index is
    below `cycles_count * 2 - 1`, so index 5 is where a three-cycle session
    ends and there is no rest after the final work.
    """
    # work@4 is the last interval of a three-cycle session.
    state = timer_state(_interval(interval=4, left=30_000), now_ms=1_000_000 + 60_000)

    assert state.is_finished is True
    assert state.interval == 5
    assert state.phase is None
    assert not state.is_running


def test_a_rest_before_the_last_work_still_runs() -> None:
    """
    The bound applies on leaving work, so rest@3 is a normal interval.
    """
    state = timer_state(_interval(interval=3, left=30_000), now_ms=1_000_000 + 60_000)

    assert state.is_finished is False
    assert state.interval == 4
    assert state.phase == "work"
