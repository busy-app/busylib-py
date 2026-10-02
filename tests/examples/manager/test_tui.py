from __future__ import annotations

from pathlib import Path

import pytest
from manager_support import (
    MANIFEST,
    RELEASE,
    RELEASES,
    FakeBar,
    manager_for,
    manager_with_catalog,
    program,
    tgz,
)
from textual.widgets import Button, DataTable, Input, Label, RichLog, Static

from busylib import types
from examples.manager.github import Reply
from examples.manager import link
from examples.manager.launcher import Launcher
from examples.manager.manager import Manager
from examples.manager.model import ManagerError
from examples.manager.model import Source
from examples.manager.tui import AppCard, AppsManager, Home

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
        assert app.sub_title == "192.168.1.20 - connected, API 27.9.0"


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

        # The source's app is on the list, not installed, and `i` installs it.
        await pilot.press("i")
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

        await pilot.press("s")
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

        await pilot.press("s")
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

        await pilot.press("s")
        await _settle(pilot)
        await pilot.press("a")
        await _settle(pilot)
        form = app.screen
        form.query_one("#f-repo", Input).value = "busy-app"
        await pilot.click("#ok")
        await _settle(pilot)

        assert app.screen is form
        assert "owner/name" in str(form.query_one("#form-error").render())
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

        await pilot.press("s")
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


# Programs from a catalog ---------------------------------------------------------


async def _settle_longer(pilot) -> None:
    """
    For flows that go through threads - a catalog is read in one.
    """
    for _ in range(12):
        await pilot.pause(0.05)


def _catalog(**extra: dict) -> dict:
    return {
        "clock": {
            **program("Clock"),
            ".env.example": b"# Where you live\nCITY=Utrecht\nAPI_KEY=\n",
        },
        "weather": program("Weather"),
        **extra,
    }


async def _open_catalog(pilot, app) -> None:
    await pilot.press("s")
    await _settle(pilot)
    await pilot.press("enter")
    await _settle_longer(pilot)


async def test_a_catalog_is_added_browsed_and_a_program_installed_after_asking(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    app = AppsManager(manager, "192.168.1.20")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("s")
        await _settle(pilot)
        await pilot.press("p")
        await _settle(pilot)
        app.screen.query_one("#f-repo", Input).value = "busy-app/programs"
        await pilot.click("#ok")
        await _settle_longer(pilot)
        assert [s.kind for s in manager.store.config.sources] == ["catalog"]

        await pilot.press("enter")  # the catalog
        await _settle_longer(pilot)
        names = [str(row[0]) for row in _rows(app)]
        assert names == ["Clock", "Weather"]

        await pilot.press("enter")  # Clock, highlighted already
        await _settle_longer(pilot)

        # Nothing is on the computer until the answer, and the question says
        # what is being agreed to.
        assert not (tmp_path / "programs" / "clock").exists()
        question = " ".join(_log(app))
        assert "Install Clock" in question and "your permissions" in question
        assert app.screen.query_one("#ask").display is True

        await pilot.click("#go")
        await _settle_longer(pilot)
        assert (tmp_path / "programs" / "clock" / "app.py").exists()
        await pilot.click("#close")
        await _settle(pilot)

        # Clock is installed now; the catalog's other program is still on offer.
        assert [row[0] for row in _rows(app)] == ["Clock", "Weather"]
        assert "busy-app/programs" in _details(app)


async def test_the_card_of_a_program_shows_how_it_will_run_against_this_bar(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    manager.launcher = Launcher(tmp_path / "logs", host="192.168.1.20")
    manager.store.add_source(Source(repo="busy-app/programs", kind="catalog"))
    catalog = await manager.catalog(manager.store.config.sources[0])
    await manager.install_program(
        await manager.prepare_program(
            manager.store.config.sources[0], catalog, catalog.apps[0]
        ),
        lambda line: None,
    )
    app = AppsManager(manager, "192.168.1.20")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)

        card = _details(app)

        assert "app.py --host 192.168.1.20" in card
        assert "{host}" not in card, "the placeholder is shown filled in"
        assert "**From** busy-app/programs" in card


async def test_typing_narrows_a_catalog_by_name_tag_or_author(tmp_path: Path) -> None:
    programs = _catalog(
        night={
            "app.py": b"x",
            "manifest.yaml": b"name: Moon\nauthor: zed\ntags:\n  - night\n",
        }
    )
    _, manager = manager_with_catalog(tmp_path, programs, _bar())
    manager.store.add_source(
        Source(repo="busy-app/programs", kind="catalog", title="Programs")
    )
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)
        await _open_catalog(pilot, app)
        assert len(_rows(app)) == 3

        app.screen.query_one("#filter", Input).value = "night"
        await _settle(pilot)
        assert [row[0] for row in _rows(app)] == ["Moon"]

        app.screen.query_one("#filter", Input).value = "ZED"
        await _settle(pilot)
        assert [row[0] for row in _rows(app)] == ["Moon"]

        app.screen.query_one("#filter", Input).value = "nothing like this"
        await _settle(pilot)
        assert _rows(app) == []
        assert "Nothing matches" in str(app.screen.query_one("#about").render())


async def test_the_catalog_shows_what_is_installed_and_what_has_changed(
    tmp_path: Path,
) -> None:
    net, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    source = Source(repo="busy-app/programs", kind="catalog", title="Programs")
    manager.store.add_source(source)
    catalog = await manager.catalog(source)
    clock = catalog.find("clock")
    assert clock is not None
    await manager.install_program(
        await manager.prepare_program(source, catalog, clock), lambda line: None
    )
    net.programs["clock"]["app.py"] = b"print('v2')\n"
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)
        await _open_catalog(pilot, app)

        states = {str(row[0]): str(row[3]) for row in _rows(app)}

    assert states == {"Clock": "update", "Weather": ""}


async def test_a_program_with_an_update_says_so_and_updating_asks_first(
    tmp_path: Path,
) -> None:
    net, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    source = Source(repo="busy-app/programs", kind="catalog", title="Programs")
    manager.store.add_source(source)
    catalog = await manager.catalog(source)
    clock = catalog.find("clock")
    assert clock is not None
    await manager.install_program(
        await manager.prepare_program(source, catalog, clock), lambda line: None
    )
    net.programs["clock"]["app.py"] = b"print('v2')\n"
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)
        assert _rows(app) == [
            ["Clock", "computer", "-", "update"],
            ["Weather", "computer", "-", "not installed"],
        ]
        assert "update available" in _details(app)

        await pilot.press("u")
        await _settle_longer(pilot)
        assert (
            tmp_path / "programs" / "clock" / "app.py"
        ).read_bytes() == b"print('hi')\n", "not before the answer"
        assert "Update Clock" in " ".join(_log(app))

        await pilot.click("#go")
        await _settle_longer(pilot)
        await pilot.click("#close")
        await _settle_longer(pilot)

        assert (
            tmp_path / "programs" / "clock" / "app.py"
        ).read_bytes() == b"print('v2')\n"
        assert _rows(app)[0][3] == "ready"


async def test_u_on_something_with_no_update_says_there_is_nothing_to_do(
    home_manager: Manager,
) -> None:
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("u")
        await _settle(pilot)

        assert app.screen is not None and not app.screen.query("#go")


async def test_settings_come_from_the_programs_own_template_and_secrets_are_masked(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    source = Source(repo="busy-app/programs", kind="catalog", title="Programs")
    manager.store.add_source(source)
    catalog = await manager.catalog(source)
    clock = catalog.find("clock")
    assert clock is not None
    await manager.install_program(
        await manager.prepare_program(source, catalog, clock), lambda line: None
    )
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)

        await pilot.press("c")
        await _settle(pilot)
        form = app.screen
        city = form.query_one("#f-CITY", Input)
        key = form.query_one("#f-API_KEY", Input)

        assert city.placeholder == "Utrecht", "the example is a hint, not a value"
        assert city.value == ""
        assert key.password is True and city.password is False

        city.value = "Rotterdam"
        key.value = "s3cret"
        await pilot.click("#ok")
        await _settle_longer(pilot)

        assert manager.store.config.externals[0].env == {
            "CITY": "Rotterdam",
            "API_KEY": "s3cret",
        }
        assert "s3cret" not in _details(app), (
            "the card names settings, never shows them"
        )  # type: ignore[attr-defined]
        assert "API_KEY" in _details(app)


async def test_a_program_that_declares_no_settings_says_so(tmp_path: Path) -> None:
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    source = Source(repo="busy-app/programs", kind="catalog")
    manager.store.add_source(source)
    catalog = await manager.catalog(source)
    weather = catalog.find("weather")
    assert weather is not None
    await manager.install_program(
        await manager.prepare_program(source, catalog, weather), lambda line: None
    )
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)

        await pilot.press("c")
        await _settle(pilot)

        assert not app.screen.query("#ok"), "no empty form"


async def test_removing_an_installed_program_asks_and_deletes_its_files(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    source = Source(repo="busy-app/programs", kind="catalog")
    manager.store.add_source(source)
    catalog = await manager.catalog(source)
    await manager.install_program(
        await manager.prepare_program(source, catalog, catalog.apps[0]),
        lambda line: None,
    )
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)

        await pilot.press("d")
        await _settle(pilot)
        assert (tmp_path / "programs" / "clock").exists(), "not before the answer"
        await pilot.press("y")
        await _settle_longer(pilot)

    assert not (tmp_path / "programs" / "clock").exists()
    assert manager.store.config.externals == []


async def test_o_opens_the_page_of_a_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr("examples.manager.tui.webbrowser.open", opened.append)
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    source = Source(repo="busy-app/programs", kind="catalog")
    manager.store.add_source(source)
    catalog = await manager.catalog(source)
    await manager.install_program(
        await manager.prepare_program(source, catalog, catalog.apps[0]),
        lambda line: None,
    )
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)

        await pilot.press("o")
        await _settle(pilot)

    assert opened == ["https://github.com/busy-app/programs/tree/main/apps/clock"]


async def test_being_offline_at_the_start_is_a_line_in_the_banner(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    manager.store.add_source(Source(repo="busy-app/programs", kind="catalog"))

    def offline(url: str, headers: dict, limit: int):
        raise ManagerError("cannot reach GitHub: offline")

    manager.github.fetch = offline
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)

        banner = app.screen.query_one("#banner", Static)

        assert banner.display is True
        assert "could not check busy-app/programs for updates" in str(banner.render())


async def test_a_catalog_that_cannot_be_read_says_so_in_its_window(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    manager.store.add_source(Source(repo="busy-app/programs", kind="catalog"))

    def broken(url: str, headers: dict, limit: int):
        raise ManagerError("cannot reach GitHub: offline")

    manager.github.fetch = broken
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)
        await _open_catalog(pilot, app)

        status = app.screen.query_one("#status")

        assert "Could not read the catalog" in str(status.render())


async def test_arrows_move_through_the_list_without_leaving_the_filter(
    tmp_path: Path,
) -> None:
    """
    Type, arrow, Enter - and the program taken is the one arrowed to, not the
    first on the list.
    """
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    manager.store.add_source(Source(repo="busy-app/programs", kind="catalog"))
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)
        await _open_catalog(pilot, app)
        assert app.screen.focused is app.screen.query_one("#filter")

        await pilot.press("down")
        await _settle(pilot)
        assert app.screen.focused is app.screen.query_one("#filter"), "still typing"
        await pilot.press("enter")
        await _settle_longer(pilot)

        assert "Install Weather" in " ".join(_log(app))


# Whether the bar is there ------------------------------------------------------------


def _toasts(app: AppsManager) -> list[str]:
    return [f"{n.title}: {n.message}" for n in app._notifications]


async def _toast(pilot, app: AppsManager, text: str) -> str:
    """
    Wait for a toast that says `text`, and return it.

    A toast is not there the moment `notify` returns: it is a message the app
    handles a little later, while the title bar changes at once. Reading the
    toasts straight after seeing the title change is a race, and a test that
    wins it on a fast machine and loses it on a slow one.
    """
    found: list[str] = []

    def seen() -> bool:
        found[:] = [t for t in _toasts(app) if text in t]
        return bool(found)

    await _until(pilot, seen)
    return found[0]


async def _until(pilot, done, seconds: float = 6.0) -> None:
    """
    Wait for something that happens on its own schedule, such as a retry.
    """
    for _ in range(int(seconds / 0.05)):
        if done():
            return
        await pilot.pause(0.05)
    raise AssertionError("it did not happen in time")


async def test_the_title_bar_says_the_bar_is_there(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, _bar())
    app = AppsManager(manager, "192.168.1.20")
    async with app.run_test(size=SIZE) as pilot:
        await _until(pilot, lambda: "connected" in app.sub_title)

        assert app.sub_title == "192.168.1.20 - connected, API 27.9.0"
        await pilot.pause(0.5)  # long enough for a toast to have shown, were there one
        assert not any("Connected" in t for t in _toasts(app)), (
            "reaching it the first time is not news"
        )


async def test_losing_the_bar_is_said_in_the_title_the_banner_and_a_toast(
    tmp_path: Path,
) -> None:
    bar = _bar(("a.app", "Alpha", "1.0.0"))
    manager = manager_for(tmp_path, bar)
    app = AppsManager(manager, "192.168.1.20")
    async with app.run_test(size=SIZE) as pilot:
        await _until(pilot, lambda: "connected" in app.sub_title)

        bar.go_away()
        await _until(pilot, lambda: "lost" in app.sub_title)

        assert app.sub_title == "192.168.1.20 - connection lost - retrying"
        toast = await _toast(pilot, app, "Lost the connection to the bar")
        assert toast.startswith("Disconnected")
        banner = app.screen.query_one("#banner", Static)
        assert banner.display is True
        assert "not answering" in str(banner.render())


async def test_the_bar_coming_back_is_said_and_the_list_is_looked_at_again(
    tmp_path: Path,
) -> None:
    """
    A bar that has been restarted may hold different apps, so the list is
    read again rather than left as it was.
    """
    bar = _bar(("a.app", "Alpha", "1.0.0"))
    manager = manager_for(tmp_path, bar)
    app = AppsManager(manager, "192.168.1.20")
    async with app.run_test(size=SIZE) as pilot:
        await _until(pilot, lambda: len(_rows(app)) == 1)
        bar.go_away()
        await _until(pilot, lambda: "lost" in app.sub_title)

        bar.apps.append(types.AppInfo(id="b.app", name="Beta", version="2"))
        bar.come_back()
        await _until(pilot, lambda: "connected" in app.sub_title)
        await _until(pilot, lambda: len(_rows(app)) == 2)

        assert (await _toast(pilot, app, "Connected again after")).startswith(
            "Connected"
        )
        assert app.screen.query_one("#banner", Static).display is False


async def test_an_update_that_changed_the_firmware_says_so_when_the_bar_returns(
    tmp_path: Path,
) -> None:
    bar = _bar()
    manager = manager_for(tmp_path, bar)
    app = AppsManager(manager, "192.168.1.20")
    async with app.run_test(size=SIZE) as pilot:
        await _until(pilot, lambda: "connected" in app.sub_title)

        bar.go_away()
        await _until(pilot, lambda: "lost" in app.sub_title)
        bar.come_back(api="28.0.0")
        await _until(pilot, lambda: "28.0.0" in app.sub_title)

        toast = await _toast(pilot, app, "went from 27.9.0 to 28.0.0")
        assert toast.startswith("Firmware changed")


async def test_a_bar_that_is_not_there_at_the_start_is_one_error_not_a_stream(
    tmp_path: Path,
) -> None:
    bar = _bar()
    bar.go_away()
    manager = manager_for(tmp_path, bar)
    app = AppsManager(manager, "192.168.1.20")
    async with app.run_test(size=SIZE) as pilot:
        await _until(pilot, lambda: "not reachable" in app.sub_title)
        await _toast(pilot, app, "Cannot reach the bar")
        await pilot.pause(2.5)  # long enough for several retries

        errors = [t for t in _toasts(app) if t.startswith("Not connected")]
        assert len(errors) == 1

        bar.come_back()
        await _until(pilot, lambda: "connected" in app.sub_title)
        await _toast(pilot, app, "Connected to the bar after")


async def test_without_a_bar_there_is_nothing_to_watch(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, None)
    app = AppsManager(manager, "")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        assert app.sub_title == "no bar"
        assert not app.workers or all(w.group != "link" for w in app.workers)


# Getting out of the running app ---------------------------------------------------


def _confirm_text(app: AppsManager) -> str:
    return " ".join(str(w.render()) for w in app.screen.query(Static))


async def test_x_asks_the_bar_to_quit_and_that_is_all_when_it_can(
    home_manager: Manager,
) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("x")
        await _settle(pilot)

        assert bar.done == ["quit"]
        assert not app.screen.query("#yes"), "no question when nothing needs asking"
        await _toast(pilot, app, "Quit the app on the bar")


async def test_a_bar_that_cannot_quit_is_asked_about_before_its_switch_is_touched(
    home_manager: Manager,
) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    bar.quit_answer = "unavailable"
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("x")
        await _settle(pilot)

        text = _confirm_text(app)
        assert "Stop the app by moving the switch?" in text
        assert "Off and back to Apps" in text and "replaced" in text
        assert bar.done == [], "nothing is pressed while the question is open"


async def test_saying_no_leaves_the_bar_exactly_as_it_was(
    home_manager: Manager,
) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    bar.quit_answer = "unavailable"
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("x", "n")
        await _settle(pilot)

        assert bar.done == []
        assert not app.screen.query("#yes")


async def test_saying_yes_leaves_the_app_by_the_switch_and_says_so(
    home_manager: Manager,
) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    bar.quit_answer = "unavailable"
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("x", "y")
        await _settle_longer(pilot)

        assert bar.done == ["switch"]
        await _toast(pilot, app, "Left the app by moving the switch")


async def test_when_nothing_is_running_there_is_no_question_and_no_switch(
    home_manager: Manager,
) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    bar.quit_answer = "none running"
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("x")
        await _settle(pilot)

        assert bar.done == []
        assert not app.screen.query("#yes")
        await _toast(pilot, app, "no app is running")


async def test_the_dashboard_asks_the_same_question(home_manager: Manager) -> None:
    bar = home_manager.bar
    assert isinstance(bar, FakeBar)
    bar.quit_answer = "unavailable"
    app = AppsManager(home_manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)
        await pilot.press("b")
        await _settle(pilot)

        await pilot.press("x", "y")
        await _settle_longer(pilot)

        assert bar.done == ["switch"]


# The bar's display, and its keys -------------------------------------------------


def _picture(app: AppsManager) -> str:
    return str(app.screen.query_one(".bar-screen").render())


def _frame_message(wire: tuple[int, int, int] = (255, 0, 0)) -> dict:
    import base64

    data = bytes(wire) * (72 * 16)
    return {
        "updates": [
            {"frame": {"screen": "FRONT", "data": base64.b64encode(data).decode()}}
        ]
    }


async def test_the_list_shows_the_bars_display_as_it_streams(tmp_path: Path) -> None:
    bar = _bar()
    app = AppsManager(manager_for(tmp_path, bar), "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)
        assert "waiting" in _picture(app)

        bar.emit(_frame_message())
        await _settle(pilot)

        assert _picture(app).count("▀") == 72 * 8


async def test_the_display_before_the_stream_says_anything_is_asked_for(
    tmp_path: Path,
) -> None:
    """
    The stream sends a frame when something changes, which on a quiet bar may
    be a long time after the manager started looking.
    """
    bar = _bar()
    bar.picture = bytes(72 * 16 * 3)
    app = AppsManager(manager_for(tmp_path, bar), "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)
        app.on_link(link.Up(api="27.9.0"))
        await _settle(pilot)

        assert "▀" in _picture(app)


async def test_losing_the_bar_blanks_the_display(tmp_path: Path) -> None:
    bar = _bar()
    app = AppsManager(manager_for(tmp_path, bar), "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)
        bar.emit(_frame_message())
        await _settle(pilot)

        app.on_link(link.Down("gone"))
        await _settle(pilot)

        assert "not connected" in _picture(app)


async def test_without_a_bar_there_is_no_display_to_show(tmp_path: Path) -> None:
    app = AppsManager(manager_for(tmp_path, None), "")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        assert app.screen.query_one("#view").display is False


async def test_the_keys_press_the_bars_keys_from_the_list(tmp_path: Path) -> None:
    bar = _bar()
    app = AppsManager(manager_for(tmp_path, bar), "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        for key in ("backspace", "k", "space", "left_square_bracket"):
            await pilot.press(key)
            await _settle(pilot)
        for key in ("right_square_bracket", "1", "2", "3", "4", "5"):
            await pilot.press(key)
            await _settle(pilot)

        assert bar.done == [
            "press BACK",
            "press OK",
            "press START",
            "press DOWN",
            "press UP",
            "press BUSY",
            "press CUSTOM",
            "press OFF",
            "press APPS",
            "press SETTINGS",
        ]
        assert isinstance(app.screen, Home), "no window opened for any of it"


async def test_the_pad_beside_the_picture_has_a_button_for_every_key(
    tmp_path: Path,
) -> None:
    bar = _bar()
    app = AppsManager(manager_for(tmp_path, bar), "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        for name in ("back", "ok", "start", "left", "right"):
            await pilot.click(f"#press-{name}")
            await _settle(pilot)
        for name in ("busy", "custom", "off", "apps", "settings"):
            await pilot.click(f"#press-{name}")
            await _settle(pilot)

    assert bar.done == [
        "press BACK",
        "press OK",
        "press START",
        "press DOWN",
        "press UP",
        "press BUSY",
        "press CUSTOM",
        "press OFF",
        "press APPS",
        "press SETTINGS",
    ]


async def test_the_picture_is_on_the_left_and_the_pad_on_the_right(
    tmp_path: Path,
) -> None:
    app = AppsManager(manager_for(tmp_path, _bar()), "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        picture = app.screen.query_one(".bar-screen").region
        pad = app.screen.query_one("#pad").region
        buttons = [app.screen.query_one(f"#press-{n}").region for n in ("back", "busy")]

        assert picture.right <= pad.x, "side by side, not stacked"
        assert picture.y == pad.y or abs(picture.y - pad.y) <= 1
        assert all(pad.contains_region(region) for region in buttons), "none cut off"


async def test_a_key_the_bar_refuses_is_said_and_nothing_else_changes(
    tmp_path: Path,
) -> None:
    bar = _bar()

    async def refuse(key) -> None:
        raise ManagerError("the bar refused to press a key")

    bar.press = refuse  # type: ignore[method-assign]
    app = AppsManager(manager_for(tmp_path, bar), "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("k")
        await _toast(pilot, app, "refused to press")

        assert isinstance(app.screen, Home)


async def test_without_a_bar_the_keys_say_so_and_do_nothing(tmp_path: Path) -> None:
    app = AppsManager(manager_for(tmp_path, None), "")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("k")
        await _toast(pilot, app, "no bar to press keys on")


# Sources, simply -----------------------------------------------------------------


async def test_a_source_is_added_by_its_name_and_appears_as_not_installed(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, _bar(), SOURCE_ROUTES)
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle(pilot)

        await pilot.press("a")
        await _settle(pilot)
        app.screen.query_one("#f-repo", Input).value = "busy-app/demo"
        await pilot.click("#ok")
        await _settle_longer(pilot)

        assert isinstance(app.screen, Home), "one question, and it is over"
        assert _rows(app) == [["Demo", "bar", "1.2.0", "not installed"]]
        assert "Not installed" in _details(app)


async def test_enter_on_something_not_installed_installs_it_after_asking(
    tmp_path: Path,
) -> None:
    bar = _bar()
    manager = manager_for(tmp_path, bar, SOURCE_ROUTES)
    await manager.add_repo("busy-app/demo")
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)

        await pilot.press("enter")  # the offer
        await _settle(pilot)
        await pilot.press("enter")  # its only version
        await _settle(pilot)
        assert bar.done == [] and app.screen.query_one("#ask").display is True

        await pilot.click("#go")
        await _settle(pilot)
        await pilot.click("#close")
        await _settle(pilot)

        assert bar.done == ["install 5"]
        assert _rows(app) == [["Demo", "bar", "1.2.0", "installed"]]


async def test_a_catalogs_program_is_installed_from_the_list_too(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(tmp_path, _catalog(), _bar())
    await manager.add_repo("busy-app/programs")
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)
        assert [row[3] for row in _rows(app)] == ["not installed", "not installed"]

        await pilot.press("i")  # Clock, under the cursor
        await _settle_longer(pilot)
        assert "Install Clock" in " ".join(_log(app))
        await pilot.click("#go")
        await _settle_longer(pilot)
        await pilot.click("#close")
        await _settle(pilot)

        assert [(r[0], r[3]) for r in _rows(app)] == [
            ("Clock", "ready"),
            ("Weather", "not installed"),
        ]


async def test_forgetting_a_source_from_its_offer_asks_and_clears_the_list(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, _bar(), SOURCE_ROUTES)
    await manager.add_repo("busy-app/demo")
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)

        await pilot.press("d")
        await _settle(pilot)
        assert "Forget the source busy-app/demo" in " ".join(
            str(w.render()) for w in app.screen.query(Label)
        )
        await pilot.press("y")
        await _settle(pilot)

        assert _rows(app) == []
    assert manager.store.config.sources == []


async def test_the_dashboard_is_for_starting_so_it_leaves_out_what_is_not_there(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, _bar(("a.app", "Alpha", "1.0.0")), SOURCE_ROUTES)
    await manager.add_repo("busy-app/demo")
    app = AppsManager(manager, "x")
    async with app.run_test(size=SIZE) as pilot:
        await _settle_longer(pilot)
        await pilot.press("b")
        await _settle_longer(pilot)

        assert [card.entry.name for card in app.screen.query(AppCard)] == ["Alpha"]
