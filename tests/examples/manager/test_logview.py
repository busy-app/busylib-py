"""
Reading the bar's log in the manager: fetched on demand, read a window at a
time, searched from end to end.
"""

from __future__ import annotations

import gzip
from pathlib import Path

from manager_support import FakeBar, manager_for
from textual.widgets import Input, TextArea

from examples.manager.logview import CHUNK, EDGE, LogScreen
from examples.manager.tui import AppsManager, Home

SIZE = (140, 44)
TOTAL = 3000


def _log(total: int = TOTAL, **special: str) -> bytes:
    """
    A log of `total` lines, each numbered, some replaced by name.
    """
    lines = [f"line {n:05d} nothing to see" for n in range(total)]
    for index, text in special.items():
        lines[int(index.removeprefix("at_"))] = text
    return "\r\n".join(lines).encode()


async def _settle(pilot) -> None:
    for _ in range(6):
        await pilot.pause(0.05)


async def _open(pilot, app: AppsManager) -> LogScreen:
    await _settle(pilot)
    await pilot.press("l")
    await _settle(pilot)
    assert isinstance(app.screen, LogScreen)
    return app.screen


def _area(screen: LogScreen) -> TextArea:
    return screen.query_one("#log", TextArea)


def _status(screen: LogScreen) -> str:
    return str(screen.query_one("#log-status").render())


async def _search(pilot, text: str) -> None:
    await pilot.press("slash")
    await _settle(pilot)
    for char in text:
        await pilot.press(char)
    await pilot.press("enter")
    await _settle(pilot)


def _app(
    tmp_path: Path, log: bytes = b"", **bar_options
) -> tuple[AppsManager, FakeBar]:
    bar = FakeBar()
    bar.log = log
    for name, value in bar_options.items():
        setattr(bar, name, value)
    return AppsManager(manager_for(tmp_path, bar), "x"), bar


async def test_the_newest_lines_are_shown_first_and_the_rest_waits(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path, _log())
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)

        text = _area(screen).text
        assert text.splitlines()[-1] == f"line {TOTAL - 1:05d} nothing to see"
        assert len(text.splitlines()) == CHUNK
        assert (screen.first, screen.last) == (TOTAL - CHUNK, TOTAL)
        assert f"Line {TOTAL} of {TOTAL}" in _status(screen)
        assert "more loads as you scroll" in _status(screen)


async def test_paging_up_to_the_top_of_the_window_loads_the_lines_before_it(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path, _log())
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)
        before = screen.first

        for _ in range(12):
            await pilot.press("pageup")
            await _settle(pilot)
            if screen.first < before:
                break

        assert screen.first == before - CHUNK
        assert _area(screen).text.splitlines()[0] == (
            f"line {screen.first:05d} nothing to see"
        )
        row = _area(screen).cursor_location[0]
        assert before <= screen.first + row < before + EDGE, "the cursor has not jumped"


async def test_paging_down_from_a_search_result_loads_the_lines_after_it(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path, _log(at_100="the needle is here"))
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)
        await _search(pilot, "needle")
        assert (screen.first, screen.last) == (0, CHUNK)

        for _ in range(12):
            await pilot.press("pagedown")
            await _settle(pilot)
            if screen.last > CHUNK:
                break

        assert screen.last == 2 * CHUNK, "more was added after the window"


async def test_g_and_shift_g_go_to_the_ends_of_the_whole_log(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, _log())
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)

        await pilot.press("g")
        await _settle(pilot)
        assert (screen.first, _area(screen).cursor_location[0]) == (0, 0)
        assert "Line 1 of" in _status(screen)

        await pilot.press("G")
        await _settle(pilot)
        assert screen.last == TOTAL
        assert f"Line {TOTAL} of" in _status(screen)


async def test_everything_in_the_box_stays_within_a_bound(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, _log(20000))
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)

        for _ in range(120):
            await pilot.press("pageup")
            await pilot.pause(0.02)
        await _settle(pilot)

        assert screen.first < 20000 - CHUNK, "it did keep loading"
        assert screen.last - screen.first <= 4 * CHUNK


async def test_a_search_finds_a_line_outside_the_window_and_marks_it(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path, _log(at_5="ERROR: the SD card fell out"))
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)
        assert screen.first > 5, "line 5 is not in the box yet"

        await _search(pilot, "sd card")

        assert screen.first <= 5 < screen.last
        assert _area(screen).selected_text == "SD card"
        assert "1 line(s) with 'sd card'" in _status(screen)


async def test_n_goes_on_to_the_next_match_and_wraps_round(tmp_path: Path) -> None:
    app, _ = _app(
        tmp_path, _log(at_10="hit one", at_1500="hit two", at_2900="hit three")
    )
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)

        def where() -> int:
            return screen.first + _area(screen).cursor_location[0]

        await _search(pilot, "hit")  # from the end, wrapping to the first
        assert where() == 10

        await pilot.press("n")
        await _settle(pilot)
        assert where() == 1500

        await pilot.press("n")
        await _settle(pilot)
        assert where() == 2900

        await pilot.press("n")
        await _settle(pilot)
        assert where() == 10, "past the last, back to the first"

        await pilot.press("N")
        await _settle(pilot)
        assert where() == 2900, "and the other way round"


async def test_a_search_with_no_match_says_so_and_changes_nothing(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path, _log())
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)
        window = (screen.first, screen.last)

        await _search(pilot, "zebra")

        assert (screen.first, screen.last) == window
        assert any("zebra" in n.message for n in app._notifications)


async def test_escape_closes_the_search_box_first_and_then_the_log(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path, _log())
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)

        await pilot.press("slash")
        await _settle(pilot)
        assert screen.query_one("#find", Input).display is True

        await pilot.press("escape")
        await _settle(pilot)
        assert screen.query_one("#find", Input).display is False
        assert isinstance(app.screen, LogScreen)

        await pilot.press("escape")
        await _settle(pilot)
        assert isinstance(app.screen, Home)


async def test_a_packed_dump_is_unpacked_before_it_is_shown(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, gzip.compress(b"first\nsecond\nthird"))
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)

        assert _area(screen).text == "first\nsecond\nthird"
        assert "Line 3 of 3" in _status(screen)


async def test_a_bar_that_will_not_give_the_log_says_why_and_r_tries_again(
    tmp_path: Path,
) -> None:
    app, bar = _app(tmp_path, b"all fine\n", log_problem="the bar is busy")
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)
        assert "the bar is busy" in _status(screen)
        assert "Press r" in _status(screen)

        bar.log_problem = ""
        await pilot.press("r")
        await _settle(pilot)

        assert _area(screen).text == "all fine"


async def test_an_empty_log_is_said_to_be_empty(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, b"")
    async with app.run_test(size=SIZE) as pilot:
        screen = await _open(pilot, app)

        assert "empty" in _status(screen)


async def test_without_a_bar_there_is_no_log_to_ask_for(tmp_path: Path) -> None:
    app = AppsManager(manager_for(tmp_path, None), "")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("l")
        await _settle(pilot)

        assert isinstance(app.screen, Home)
        assert any("no bar to read logs" in n.message for n in app._notifications)
