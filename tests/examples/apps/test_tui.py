from __future__ import annotations

from pathlib import Path

import pytest
from apps_support import MANIFEST, RELEASE, RELEASES, FakeBar, manager_for, tgz
from textual.widgets import Button, DataTable, Input, RichLog, Static

from busylib import types
from examples.apps.github import Reply
from examples.apps.manager import Manager
from examples.apps.model import Source
from examples.apps.tui import AppCard, AppsManager

SIZE = (140, 44)

SOURCE_ROUTES = {
    RELEASES: [RELEASE],
    "https://dl/demo.tgz": Reply(
        200, tgz({"appmeta/manifest.json": MANIFEST, "main.js": b"x"})
    ),
    "https://raw.githubusercontent.com/busy-app/demo/v1.2.0/src/appmeta/manifest.json": Reply(
        200, MANIFEST
    ),
}


def _bar(*apps: tuple[str, str, str]) -> FakeBar:
    return FakeBar([types.AppInfo(id=i, name=n, version=v) for i, n, v in apps])


async def _settle(pilot) -> None:
    """
    Let the messages and the work they cause run to a stop.

    Not `workers.wait_for_complete()`: a worker that is waiting for a window
    to be answered is working as intended and never completes while the
    window is open, so waiting for it would wait for the test to time out.
    """
    for _ in range(4):
        await pilot.pause(0.05)


def _rows(app: AppsManager) -> list[list[str]]:
    table = app.screen.query_one(DataTable)
    return [[str(cell) for cell in table.get_row_at(i)] for i in range(table.row_count)]


def _details(app: AppsManager) -> str:
    return app.screen.card  # type: ignore[attr-defined]


@pytest.fixture
def home_manager(tmp_path: Path) -> Manager:
    manager = manager_for(
        tmp_path,
        _bar(("a.app", "Alpha", "1.0.0"), ("b.app", "Beta", "2.0.0")),
        SOURCE_ROUTES,
    )
    manager.add_external("Clock", str(tmp_path), "echo hi", "Draws a clock")
    return manager


async def test_the_list_has_the_bars_apps_and_the_computers(
    home_manager: Manager,
) -> None:
    app = AppsManager(home_manager, "192.168.1.20")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        assert _rows(app) == [
            ["Alpha", "bar", "1.0.0", "installed"],
            ["Beta", "bar", "2.0.0", "installed"],
            ["Clock", "computer", "-", "ready"],
        ]
        assert app.sub_title == "192.168.1.20"


async def test_the_card_follows_the_cursor(home_manager: Manager) -> None:
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)
        assert "Alpha" in _details(app) and "launch" in _details(app)

        await pilot.press("down", "down")
        await _settle(pilot)

        assert "Draws a clock" in _details(app)
        assert "echo hi" in _details(app)


async def test_enter_launches_what_is_selected_on_the_bar(
    home_manager: Manager,
) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("enter")
        await _settle(pilot)

    assert bar.done == ["launch a.app"]


async def test_a_bar_that_is_not_there_is_a_banner_not_a_blank_screen(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, None)
    manager.add_external("Clock", str(tmp_path), "echo hi", "")
    app = AppsManager(manager, "")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        banner = app.screen.query_one("#banner", Static)
        assert banner.display is True
        assert "--offline" in str(banner.render())
        assert [row[0] for row in _rows(app)] == ["Clock"]


async def test_removing_a_bar_app_asks_first_and_then_does_it(
    home_manager: Manager,
) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("d")
        await _settle(pilot)
        assert bar.done == [], "nothing happens before the answer"
        await pilot.press("y")
        await _settle(pilot)

        assert bar.done == ["delete a.app"]
        assert [row[0] for row in _rows(app)] == ["Beta", "Clock"]


async def test_cancelling_a_removal_removes_nothing(home_manager: Manager) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("d", "n")
        await _settle(pilot)

        assert bar.done == []
        assert len(_rows(app)) == 3


async def test_a_program_from_this_computer_can_be_added_from_the_list(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, _bar())
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("e")
        await _settle(pilot)
        form = app.screen
        form.query_one("#f-name", Input).value = "Meeting light"
        form.query_one("#f-path", Input).value = str(tmp_path)
        form.query_one("#f-command", Input).value = "python light.py"
        await pilot.click("#ok")
        await _settle(pilot)

        assert [row[0] for row in _rows(app)] == ["Meeting light"]
    assert manager.store.config.externals[0].command == "python light.py"


async def test_a_form_that_cannot_be_saved_says_where_and_stays_open(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, _bar())
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("e")
        await _settle(pilot)
        form = app.screen
        form.query_one("#f-name", Input).value = "Nowhere"
        form.query_one("#f-path", Input).value = str(tmp_path / "missing")
        form.query_one("#f-command", Input).value = "run"
        await pilot.click("#ok")
        await _settle(pilot)

        assert app.screen is form, "the form stays open"
        assert "is not a folder" in str(form.query_one("#form-error").render())
        assert form.query_one("#f-name", Input).value == "Nowhere", (
            "and keeps what was typed"
        )
    assert manager.store.config.externals == []


async def test_installing_from_a_source_goes_through_asking(tmp_path: Path) -> None:
    bar = _bar()
    manager = manager_for(tmp_path, bar, SOURCE_ROUTES)
    manager.store.add_source(Source(repo="busy-app/demo", title="Demo"))
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("i")
        await _settle(pilot)
        await pilot.press("enter")  # the source
        await _settle(pilot)
        await pilot.press("enter")  # its only version
        await _settle(pilot)

        # Held by the bar, and waiting for the go-ahead.
        assert bar.done == []
        assert bar.staged_package
        assert app.screen.query_one("#ask").display is True

        await pilot.click("#go")
        await _settle(pilot)

        assert bar.done == ["install 5"]
        await pilot.click("#close")
        await _settle(pilot)
        assert [row[0] for row in _rows(app)] == ["Demo"]


async def test_saying_no_at_the_question_installs_nothing(tmp_path: Path) -> None:
    bar = _bar()
    manager = manager_for(tmp_path, bar, SOURCE_ROUTES)
    manager.store.add_source(Source(repo="busy-app/demo"))
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("i")
        await _settle(pilot)
        await pilot.press("enter")
        await _settle(pilot)
        await pilot.press("enter")
        await _settle(pilot)
        await pilot.click("#stop")
        await _settle(pilot)

    assert bar.done == []
    assert bar.apps == []


async def test_a_package_that_is_wrong_ends_the_install_with_the_reason(
    tmp_path: Path,
) -> None:
    bar = _bar()
    routes = {**SOURCE_ROUTES, "https://dl/demo.tgz": Reply(200, b"not a package")}
    manager = manager_for(tmp_path, bar, routes)
    manager.store.add_source(Source(repo="busy-app/demo"))
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("i")
        await _settle(pilot)
        await pilot.press("enter")
        await _settle(pilot)
        await pilot.press("enter")
        await _settle(pilot)

        assert app.screen.has_class("failed")
        assert app.screen.query_one("#end").display is True

    assert bar.staged_package == b""


async def test_a_source_is_added_from_the_sources_window(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, _bar(), SOURCE_ROUTES)
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("i")
        await _settle(pilot)
        await pilot.press("a")
        await _settle(pilot)
        app.screen.query_one("#f-repo", Input).value = "busy-app/demo"
        await pilot.click("#ok")
        await _settle(pilot)

    assert [(s.repo, s.title) for s in manager.store.config.sources] == [
        ("busy-app/demo", "Demo")
    ]


async def test_a_mistyped_repository_is_explained_in_the_form(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, _bar(), SOURCE_ROUTES)
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("i")
        await _settle(pilot)
        await pilot.press("a")
        await _settle(pilot)
        form = app.screen
        form.query_one("#f-repo", Input).value = "busy-app"
        await pilot.click("#ok")
        await _settle(pilot)

        assert app.screen is form
        assert "owner/name" in str(form.query_one("#e-repo").render())
    assert manager.store.config.sources == []


async def test_the_dashboard_shows_cards_for_both_kinds_and_starts_them(
    home_manager: Manager,
) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("b")
        await _settle(pilot)

        cards = list(app.screen.query(AppCard))
        assert [card.entry.name for card in cards] == ["Alpha", "Beta", "Clock"]

        await pilot.press("right", "enter")
        await _settle(pilot)

        assert bar.done == ["launch b.app"]

        await pilot.press("escape")
        await _settle(pilot)
        assert len(_rows(app)) == 3


def _log(app: AppsManager) -> list[str]:
    log = app.screen.query_one("#log", RichLog)
    return ["".join(segment.text for segment in line).strip() for line in log.lines]


async def test_the_question_comes_after_what_it_is_about(tmp_path: Path) -> None:
    """
    Lines from the work and the question were written by two routes, and the
    question could land above the lines it was asking about. A bar whose
    answers never wait made it visible; a real one only hid it.
    """
    manager = manager_for(tmp_path, _bar(), SOURCE_ROUTES)
    manager.store.add_source(Source(repo="busy-app/demo"))
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("i")
        await _settle(pilot)
        await pilot.press("enter")
        await _settle(pilot)
        await pilot.press("enter")
        await _settle(pilot)

        lines = _log(app)

    assert lines[-1] == "Install Demo 1.2.0. Go ahead?"
    assert lines.index("handing it to the bar") < lines.index(lines[-1])
    assert lines[0].startswith("downloading")


@pytest.mark.parametrize("key", ["e", "i"])
async def test_a_form_in_a_short_terminal_still_shows_its_buttons(
    tmp_path: Path, key: str
) -> None:
    """
    The buttons were pushed off the bottom by the fields above them, and a
    form that cannot be confirmed with the mouse or seen to be closable is a
    trap. Checked at a size people really have, not the roomy one.
    """
    manager = manager_for(tmp_path, _bar(), SOURCE_ROUTES)
    app = AppsManager(manager, "x")
    async with app.run_test(size=(100, 26)) as pilot:
        await _settle(pilot)

        await pilot.press(key)
        await _settle(pilot)
        if key == "i":
            await pilot.press("a")
            await _settle(pilot)

        for button in app.screen.query(Button):
            region = button.region
            assert region.height > 0 and region.bottom <= app.size.height, button.id
