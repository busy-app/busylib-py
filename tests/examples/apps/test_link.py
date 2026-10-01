from __future__ import annotations

import pytest

from examples.apps.link import POLL, RETRY, Down, Event, Up, watch
from examples.apps.model import ManagerError


class Over(Exception):
    """
    The script has run out; the watch would go on forever.
    """


class Scripted:
    """
    A bar that does what it is told, in order, and a clock that only moves when
    the watch sleeps.

    `versions` and `holds` are the answers to successive questions: a string or
    None is an answer, an exception is raised. `holds` entries of None mean the
    socket closed cleanly.
    """

    def __init__(self, versions: list, holds: list | None = None) -> None:
        self.versions = list(versions)
        self.holds = list(holds or [])
        self.events: list[Event] = []
        self.slept: list[float] = []
        self.time = 0.0
        self.asked = 0

    async def version(self) -> str:
        self.asked += 1
        if not self.versions:
            raise Over
        answer = self.versions.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def hold(self) -> None:
        if not self.holds:
            raise Over
        answer = self.holds.pop(0)
        self.time += 30  # a socket is open for a while before it ends
        if isinstance(answer, Exception):
            raise answer

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.time += seconds

    def now(self) -> float:
        return self.time

    async def run(self) -> None:
        with pytest.raises(Over):
            await watch(self, self.events.append, sleep=self.sleep, now=self.now)


GONE = ManagerError("the bar did not answer")


async def test_reaching_the_bar_the_first_time_is_reported_once() -> None:
    bar = Scripted(["27.9.0"], [Over()])

    await bar.run()

    assert bar.events[0] == Up(api="27.9.0", previous="", after=None)


async def test_a_bar_that_goes_and_comes_back_is_reported_both_ways() -> None:
    bar = Scripted(
        ["27.9.0", GONE, GONE, "27.9.0"],
        [ManagerError("the connection closed"), Over()],
    )

    await bar.run()

    kinds = [type(e).__name__ for e in bar.events]
    assert kinds == ["Up", "Down", "Up"]
    down = bar.events[1]
    assert isinstance(down, Down) and down.first is False
    back = bar.events[2]
    assert isinstance(back, Up) and back.previous == "27.9.0"
    assert back.after is not None and back.after > 0


async def test_a_firmware_update_shows_as_a_changed_version() -> None:
    bar = Scripted(["27.9.0", GONE, "28.1.0"], [ManagerError("closed"), Over()])

    await bar.run()

    back = bar.events[-1]
    assert isinstance(back, Up)
    assert (back.previous, back.api) == ("27.9.0", "28.1.0")


async def test_a_bar_that_is_not_there_at_the_start_is_one_complaint_not_many() -> None:
    """
    Retrying is not news; the person was told once.
    """
    bar = Scripted([GONE, GONE, GONE, GONE, "27.9.0"], [Over()])

    await bar.run()

    downs = [e for e in bar.events if isinstance(e, Down)]
    assert len(downs) == 1
    assert downs[0].first is True, (
        "it never answered, which is not the same as losing it"
    )
    assert isinstance(bar.events[-1], Up)
    assert bar.events[-1].after is not None


async def test_the_wait_between_tries_grows_and_stops_growing() -> None:
    bar = Scripted([GONE] * 8 + ["27.9.0"], [Over()])

    await bar.run()

    assert bar.slept[:8] == [*RETRY, RETRY[-1], RETRY[-1], RETRY[-1]]


async def test_the_wait_starts_over_after_the_bar_has_been_there() -> None:
    """
    A long outage must not leave the next one waiting as if it were still the
    same one: after a return the first retry is the short one again.
    """
    bar = Scripted(
        ["27.9.0", GONE, GONE, GONE, "27.9.0", GONE, GONE, "27.9.0"],
        [ManagerError("closed"), ManagerError("closed"), Over()],
    )

    await bar.run()

    # First outage: 1 after the loss, then 1, 2. Second: 1 after the loss,
    # then 1 - not the 4 or 8 the first outage had grown to.
    assert bar.slept == [1.0, 1.0, 2.0, 1.0, 1.0]


async def test_a_socket_that_fails_for_its_own_reasons_is_not_a_lost_bar() -> None:
    """
    A firmware without the endpoint, or a proxy that will not pass sockets,
    makes `hold` fail at once while the bar is perfectly well. That must not
    flash "connection lost" every second.
    """
    bar = Scripted(
        ["27.9.0", "27.9.0", "27.9.0", GONE],
        [ManagerError("Status WebSocket streaming failed")],
    )

    await bar.run()

    kinds = [type(e).__name__ for e in bar.events]
    assert kinds == ["Up", "Down"], "quiet polling, and one loss when it really goes"
    assert bar.slept[0] == POLL


async def test_polling_stops_trying_the_socket_again() -> None:
    bar = Scripted(
        ["27.9.0", "27.9.0", "27.9.0", "27.9.0", Over()], [ManagerError("no")]
    )

    await bar.run()

    assert bar.holds == [], "it was tried once and given up on"


async def test_the_socket_is_tried_again_after_the_bar_has_been_away() -> None:
    bar = Scripted(
        ["27.9.0", "27.9.0", GONE, "27.9.0"],
        [ManagerError("no"), Over()],
    )

    await bar.run()

    assert bar.holds == [], "both holds were used: the second after the return"


async def test_the_reason_for_a_loss_is_what_the_connection_said() -> None:
    bar = Scripted(
        ["27.9.0", GONE],
        [ManagerError("the connection broke (reset by peer)")],
    )

    await bar.run()

    down = next(e for e in bar.events if isinstance(e, Down))
    assert down.reason == "the connection broke (reset by peer)"
    assert down.first is False


async def test_a_socket_that_closes_cleanly_while_the_bar_answers_is_not_a_loss() -> (
    None
):
    bar = Scripted(["27.9.0", "27.9.0", Over()], [None])

    await bar.run()

    assert [type(e).__name__ for e in bar.events] == ["Up"]
