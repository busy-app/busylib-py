"""
Changing a timer: what snapshot each change writes, and why.

There is no endpoint that pauses a session or moves it on a phase. Every
change is a snapshot write, and the device takes the freshest snapshot as
the truth - so these tests pin down the snapshot each helper produces.
"""

from __future__ import annotations

import pytest

from busylib import types
from busylib.features import timer

SETTINGS = types.BusyBarSettings(
    theme="busy", show_work_phase_only=False, trigger_smart_home=True
)
WORK = 20 * 60 * 1000
REST = 5 * 60 * 1000
CARD = "00000000-0000-0000-0000-000000000000"
INTERVAL_SETTINGS = types.BusySnapshotIntervalSettings(
    type="INTERVAL",
    interval_work_ms=WORK,
    interval_rest_ms=REST,
    interval_work_cycles_count=3,
    is_autostart_enabled=False,
)


class FakeBar:
    """
    A bar that remembers what was written to it.

    Only the four calls the helpers make, so a test can say what the
    device holds and then read back the snapshot that was sent.
    """

    def __init__(
        self,
        snapshot: types.BusySnapshotVariant,
        *,
        timer_settings: types.BusyTimerSettings | None = None,
        stamp: int = 1_000_000,
    ) -> None:
        self.held = types.BusySnapshot(snapshot=snapshot, snapshot_timestamp_ms=stamp)
        self.timer_settings = timer_settings or INTERVAL_SETTINGS
        self.written: list[types.BusySnapshot] = []
        self.profiles_written: list[types.BusyProfile] = []

    async def busy_snapshot(self) -> types.BusySnapshot:
        return self.held

    async def busy_snapshot_set(
        self, snapshot: types.BusySnapshot
    ) -> types.SuccessResponse:
        self.written.append(snapshot)
        self.held = snapshot
        return types.SuccessResponse(result="OK")

    async def busy_profile(self, slot: types.BusyProfileSlot) -> types.BusyProfile:
        return types.BusyProfile(
            sort_order=0,
            title=slot.upper(),
            id=CARD,
            timer_settings=self.timer_settings,
            busy_bar_settings=SETTINGS,
            profile_timestamp_ms=1,
        )

    async def busy_profile_set(
        self, slot: types.BusyProfileSlot, profile: types.BusyProfile
    ) -> types.SuccessResponse:
        self.profiles_written.append(profile)
        return types.SuccessResponse(result="OK")

    async def storage_list(self, path: str) -> types.StorageList:
        return types.StorageList(
            list=[
                types.StorageDirElement(type="dir", name=name)
                for name in ("dnd", "lunch", "meeting")
            ]
        )

    @property
    def last(self) -> types.BusySnapshotVariant:
        return self.written[-1].snapshot


def _not_started() -> types.BusySnapshotNotStarted:
    return types.BusySnapshotNotStarted(type="NOT_STARTED", busy_bar_settings=SETTINGS)


def _running(
    *, interval: int = 0, left: int = WORK, paused: bool = False
) -> types.BusySnapshotInterval:
    return types.BusySnapshotInterval(
        type="INTERVAL",
        card_id=CARD,
        current_interval=interval,
        current_interval_time_total_ms=WORK if interval % 2 == 0 else REST,
        current_interval_time_left_ms=left,
        is_paused=paused,
        interval_settings=INTERVAL_SETTINGS,
        busy_bar_settings=SETTINGS,
    )


async def test_start_builds_the_session_the_card_describes() -> None:
    """
    The mode comes from the card, not from the caller: the device rejects
    a snapshot that disagrees with the card it names.
    """
    bar = FakeBar(_not_started())

    await timer.start(bar, "busy", now_ms=5_000_000)

    written = bar.last
    assert isinstance(written, types.BusySnapshotInterval)
    assert written.card_id == CARD
    assert written.current_interval == 0
    assert written.current_interval_time_left_ms == WORK
    assert written.is_paused is False
    # The write is stamped with the moment of writing, since the freshest
    # snapshot is the one the device believes.
    assert bar.written[-1].snapshot_timestamp_ms == 5_000_000


async def test_start_follows_a_countdown_card() -> None:
    """
    A card holding a countdown starts a countdown, at its own length.
    """
    bar = FakeBar(
        _not_started(),
        timer_settings=types.BusyTimerSimpleSettings(
            type="SIMPLE", total_time_ms=90_000
        ),
    )

    await timer.start(bar)

    written = bar.last
    assert isinstance(written, types.BusySnapshotSimple)
    assert written.time_left_ms == 90_000


async def test_start_can_override_the_theme_for_one_session() -> None:
    """
    The card keeps its own theme, so the override lasts as long as the
    session and no longer.
    """
    bar = FakeBar(_not_started())

    await timer.start(bar, theme="meeting")

    assert bar.last.busy_bar_settings.theme == "meeting"
    assert not bar.profiles_written


async def test_pausing_writes_back_the_time_actually_left() -> None:
    """
    The stored snapshot's figure was true when it was written. Pausing
    without recomputing would hand back the time the session already
    spent - here, five minutes of it.
    """
    bar = FakeBar(_running(left=WORK), stamp=1_000_000)

    await timer.set_paused(bar, True, now_ms=1_000_000 + 5 * 60 * 1000)

    written = bar.last
    assert isinstance(written, types.BusySnapshotInterval)
    assert written.is_paused is True
    assert written.current_interval_time_left_ms == WORK - 5 * 60 * 1000


async def test_pausing_carries_a_session_that_moved_on() -> None:
    """
    If the phase changed since the snapshot was written, pausing has to
    record which phase the session is actually in.
    """
    bar = FakeBar(_running(interval=0, left=WORK), stamp=1_000_000)

    # Past the whole work phase and a minute into the rest.
    await timer.set_paused(bar, True, now_ms=1_000_000 + WORK + 60_000)

    written = bar.last
    assert isinstance(written, types.BusySnapshotInterval)
    assert written.current_interval == 1
    assert written.current_interval_time_total_ms == REST
    assert written.current_interval_time_left_ms == REST - 60_000


async def test_resuming_only_clears_the_flag() -> None:
    """
    A paused snapshot already holds the right remaining time, so resuming
    must not recompute it.
    """
    bar = FakeBar(_running(left=90_000, paused=True), stamp=1_000_000)

    await timer.set_paused(bar, False, now_ms=1_000_000 + 60 * 60 * 1000)

    written = bar.last
    assert isinstance(written, types.BusySnapshotInterval)
    assert written.is_paused is False
    assert written.current_interval_time_left_ms == 90_000


async def test_next_phase_moves_on_at_full_length() -> None:
    """
    Work becomes rest at the rest length, not at whatever was left.
    """
    bar = FakeBar(_running(interval=0, left=WORK), stamp=1_000_000)

    await timer.next_phase(bar, now_ms=1_000_000)

    written = bar.last
    assert isinstance(written, types.BusySnapshotInterval)
    assert written.current_interval == 1
    assert written.current_interval_time_left_ms == REST


async def test_next_phase_past_the_last_interval_ends_the_session() -> None:
    """
    Three work cycles means intervals 0 to 5, so there is nothing after
    the last rest to move to.
    """
    bar = FakeBar(_running(interval=5, left=REST), stamp=1_000_000)

    await timer.next_phase(bar, now_ms=1_000_000)

    assert isinstance(bar.last, types.BusySnapshotNotStarted)


async def test_stop_writes_not_started() -> None:
    bar = FakeBar(_running())

    await timer.stop(bar, now_ms=2_000_000)

    assert isinstance(bar.last, types.BusySnapshotNotStarted)


async def test_the_session_theme_is_written_to_the_session() -> None:
    bar = FakeBar(_running())

    await timer.set_session_theme(bar, "dnd", now_ms=1_000_000)

    assert bar.last.busy_bar_settings.theme == "dnd"
    assert not bar.profiles_written


async def test_the_card_theme_is_written_to_the_card() -> None:
    """
    A card's theme outlasts the session, and does not touch what is on
    screen now.
    """
    bar = FakeBar(_running())

    await timer.set_card_theme(bar, "custom", "lunch")

    assert bar.profiles_written[-1].busy_bar_settings.theme == "lunch"
    assert not bar.written


@pytest.mark.parametrize(
    "call",
    [
        lambda bar: timer.set_paused(bar, True),
        lambda bar: timer.next_phase(bar),
        lambda bar: timer.set_session_theme(bar, "dnd"),
    ],
)
async def test_changes_that_need_a_session_say_so(call) -> None:
    """
    With nothing running there is nothing to rewrite, and writing a
    session to make the change possible would start one nobody asked for.
    """
    bar = FakeBar(_not_started())

    with pytest.raises(timer.TimerNotRunningError):
        await call(bar)

    assert not bar.written


async def test_a_card_write_is_stamped_with_now() -> None:
    """
    The device keeps whichever copy of a card is newer and silently drops
    the rest, answering OK either way. A card read back and written
    unchanged carries the stored timestamp - and a bar fresh from the
    factory reports 0 - so the write has to carry its own.
    """
    bar = FakeBar(_not_started())

    await timer.set_card_theme(bar, "busy", "lunch", now_ms=7_000_000)

    written = bar.profiles_written[-1]
    assert written.profile_timestamp_ms == 7_000_000
    assert written.busy_bar_settings.theme == "lunch"


class FakeAssets:
    """A bar with a themes directory and two cards."""

    def __init__(self, *names: str, card_theme: str = "busy") -> None:
        self.names = names
        self.card_theme = card_theme
        self.asked: list[str] = []

    async def storage_list(self, path: str) -> types.StorageList:
        self.asked.append(path)
        return types.StorageList(
            list=[types.StorageDirElement(type="dir", name=name) for name in self.names]
        )

    async def busy_profile(self, slot: types.BusyProfileSlot) -> types.BusyProfile:
        return types.BusyProfile(
            sort_order=0,
            title=slot.upper(),
            id=CARD,
            timer_settings=INTERVAL_SETTINGS,
            busy_bar_settings=SETTINGS.model_copy(update={"theme": self.card_theme}),
            profile_timestamp_ms=1,
        )


async def test_themes_are_read_from_the_bar() -> None:
    """
    Themes are assets: one bar has what the firmware shipped, another has
    one its owner uploaded, a third is missing one its owner deleted. So
    the set is read rather than written down where it would go stale.
    """
    bar = FakeAssets("meeting", "dnd", "lunch", card_theme="dnd")

    assert await timer.themes(bar) == ["dnd", "lunch", "meeting"]
    assert bar.asked == [timer.THEMES_PATH]


async def test_a_theme_a_card_uses_counts_even_without_a_directory() -> None:
    """
    The firmware's built-in default has no asset directory, so a listing
    alone would report that a bar cannot show the theme it is showing
    right now. A theme one of its own cards is set to is real by
    definition - and this is what makes the default survive being renamed
    in a future firmware, rather than a constant here going stale.
    """
    assert await timer.themes(FakeAssets("lunch", card_theme="busy")) == [
        "busy",
        "lunch",
    ]


async def test_a_theme_the_bar_does_not_have_is_refused() -> None:
    """
    The device stores a theme that does not exist and reads it back
    happily - confirmed on firmware r971, where a card set to
    "no_such_theme_at_all" came back as exactly that - so the check has
    to happen here or every layer reports success.
    """
    bar = FakeBar(_running())

    with pytest.raises(timer.UnknownThemeError, match="no theme 'meating'"):
        await timer.set_session_theme(bar, "meating")
    with pytest.raises(timer.UnknownThemeError) as refused:
        await timer.set_card_theme(bar, "busy", "meating")

    assert refused.value.available == ["busy", "dnd", "lunch", "meeting"]
    assert not bar.written
    assert not bar.profiles_written


async def test_a_known_set_can_be_passed_in_to_save_the_lookup() -> None:
    """
    A caller that already listed the themes - to offer them to someone -
    should not make the bar list them again on every write.
    """
    bar = FakeBar(_running())

    await timer.set_card_theme(bar, "busy", "whatever", known=["whatever"])

    assert bar.profiles_written[-1].busy_bar_settings.theme == "whatever"


def test_both_errors_are_importable_from_the_package() -> None:
    """
    A caller catching one of these should not have to know which module
    it lives in - and having to import one from `busylib.features` and
    the other from `busylib.features.timer` is the kind of inconsistency
    nobody discovers until it bites.
    """
    from busylib import features

    assert features.TimerNotRunningError is timer.TimerNotRunningError
    assert features.UnknownThemeError is timer.UnknownThemeError
    assert {"TimerNotRunningError", "UnknownThemeError"} <= set(features.__all__)
