from __future__ import annotations

from pathlib import Path

import pytest
from apps_support import (
    MANIFEST,
    RELEASE,
    RELEASES,
    CatalogNet,
    FakeBar,
    manager_for,
    program,
    tgz,
)

from busylib import types
from examples.apps import package
from examples.apps.bar import CannotQuitDirectly
from examples.apps.github import Reply
from examples.apps.manager import Entry, Manager
from examples.apps.model import Asset, ExternalApp, ManagerError, Source, Version
from examples.apps.store import Store


@pytest.mark.asyncio
async def test_the_list_is_what_the_bar_has_then_what_the_computer_has(
    tmp_path: Path,
) -> None:
    bar = FakeBar(
        [
            types.AppInfo(id="b.app", name="Beta", version="1"),
            types.AppInfo(id="a.app", name="alpha", version="2"),
        ]
    )
    manager = manager_for(tmp_path, bar)
    manager.add_external("Clock", str(tmp_path), "run", "")

    entries, problem = await manager.entries()

    assert problem == ""
    assert [(e.name, e.where) for e in entries] == [
        ("alpha", "bar"),
        ("Beta", "bar"),
        ("Clock", "computer"),
    ]


@pytest.mark.asyncio
async def test_a_bar_that_does_not_answer_does_not_hide_the_external_apps(
    tmp_path: Path,
) -> None:
    bar = FakeBar()
    bar.broken = "the bar at 1.2.3.4 did not answer"
    manager = manager_for(tmp_path, bar)
    manager.add_external("Clock", str(tmp_path), "run", "")

    entries, problem = await manager.entries()

    assert [e.name for e in entries] == ["Clock"]
    assert "did not answer" in problem


@pytest.mark.asyncio
async def test_without_a_bar_the_list_says_so_and_still_has_the_rest(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, None)
    manager.add_external("Clock", str(tmp_path), "run", "")

    entries, problem = await manager.entries()

    assert len(entries) == 1 and "--offline" in problem


@pytest.mark.asyncio
async def test_installing_a_release_downloads_checks_stages_and_waits_for_the_go_ahead(
    tmp_path: Path,
) -> None:
    bar = FakeBar()
    release = tgz({"appmeta/manifest.json": MANIFEST, "main.js": b"x"})
    manager = manager_for(
        tmp_path,
        bar,
        {RELEASES: [RELEASE], "https://dl/demo.tgz": Reply(200, release)},
    )
    source = Source(repo="busy-app/demo")
    (version,) = await manager.versions(source)
    said: list[str] = []

    prepared = await manager.prepare(source, version, said.append)

    # Held by the bar, not yet installed.
    assert bar.done == []
    assert prepared.summary == "Install Demo 1.2.0."
    assert any("downloading demo.tgz" in line for line in said)
    assert any("handing it to the bar" in line for line in said)

    await manager.commit(prepared)

    assert bar.done == ["install 5"]
    entries, _ = await manager.entries()
    assert [e.ident for e in entries] == ["demo.app"]


@pytest.mark.asyncio
async def test_what_an_install_replaces_is_said_before_it_happens(
    tmp_path: Path,
) -> None:
    bar = FakeBar([types.AppInfo(id="demo.app", name="Demo", version="1.0.0")])
    release = tgz({"appmeta/manifest.json": MANIFEST})
    manager = manager_for(
        tmp_path, bar, {RELEASES: [RELEASE], "https://dl/demo.tgz": Reply(200, release)}
    )
    source = Source(repo="busy-app/demo")
    (version,) = await manager.versions(source)

    prepared = await manager.prepare(source, version, lambda line: None)

    assert prepared.summary == "Replace Demo 1.0.0 with 1.2.0."


@pytest.mark.asyncio
async def test_a_release_that_is_not_an_application_never_reaches_the_bar(
    tmp_path: Path,
) -> None:
    bar = FakeBar()
    manager = manager_for(
        tmp_path,
        bar,
        {
            RELEASES: [RELEASE],
            "https://dl/demo.tgz": Reply(200, b"<html>not a package"),
        },
    )
    source = Source(repo="busy-app/demo")
    (version,) = await manager.versions(source)

    with pytest.raises(ManagerError, match="not a tar or tgz"):
        await manager.prepare(source, version, lambda line: None)

    assert bar.staged_package == b""


@pytest.mark.asyncio
async def test_installing_with_no_bar_says_why_it_cannot(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, None)
    version = Version("v1", "v1", "release", Asset("a.tgz", "https://dl/a.tgz"))

    with pytest.raises(ManagerError, match="--offline"):
        await manager.prepare(Source(repo="a/b"), version, lambda line: None)


@pytest.mark.asyncio
async def test_a_build_source_is_downloaded_built_and_packed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package.shutil, "which", lambda name: f"/bin/{name}")
    commands: list[list[str]] = []

    def build(argv: list[str], cwd: Path) -> tuple[int, str]:
        if argv[1:] == ["--version"]:
            return 0, "v25.2.1\n"
        commands.append(argv[1:])
        if argv[1:] == ["run", "build"]:
            out = cwd / "dist/demo.app/appmeta"
            out.mkdir(parents=True)
            (out / "manifest.json").write_bytes(MANIFEST)
        return 0, ""

    archive = tgz(
        {
            "busy-app-demo-abc/src/appmeta/manifest.json": MANIFEST,
            "busy-app-demo-abc/pnpm-lock.yaml": b"",
        }
    )
    bar = FakeBar()
    manager = manager_for(
        tmp_path,
        bar,
        {"https://codeload.github.com/busy-app/demo/tar.gz/main": Reply(200, archive)},
        run=build,
    )
    source = Source(repo="busy-app/demo", mode="build")
    said: list[str] = []

    prepared = await manager.prepare(
        source, Version("main", "main (latest)", "branch"), said.append
    )

    assert commands == [["install", "--frozen-lockfile"], ["run", "build"]]
    assert prepared.package.manifest.id == "demo.app"
    assert any("building" in line for line in said)


@pytest.mark.asyncio
async def test_a_package_the_bar_reads_as_something_else_is_not_installed(
    tmp_path: Path,
) -> None:
    class Confused(FakeBar):
        async def stage(self, package: bytes) -> types.AppStageResult:
            return types.AppStageResult(
                result="OK",
                install_key=1,
                staged=types.AppInfo(id="other.app", name="Other", version="9"),
            )

    release = tgz({"appmeta/manifest.json": MANIFEST})
    manager = manager_for(
        tmp_path,
        Confused(),
        {RELEASES: [RELEASE], "https://dl/demo.tgz": Reply(200, release)},
    )
    source = Source(repo="busy-app/demo")
    (version,) = await manager.versions(source)

    with pytest.raises(ManagerError, match="read the package as 'other.app'"):
        await manager.prepare(source, version, lambda line: None)


@pytest.mark.asyncio
async def test_a_source_is_checked_and_named_before_it_is_kept(tmp_path: Path) -> None:
    manager = manager_for(
        tmp_path,
        FakeBar(),
        {
            RELEASES: [RELEASE],
            "https://raw.githubusercontent.com/busy-app/demo/v1.2.0/src/appmeta/manifest.json": Reply(
                200, MANIFEST
            ),
        },
    )

    source = await manager.add_source(Source(repo="busy-app/demo"))

    assert source.title == "Demo"
    assert Store(tmp_path / "apps.db").load().sources[0].title == "Demo"


@pytest.mark.asyncio
async def test_a_source_that_cannot_be_installed_from_is_not_kept(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, FakeBar())

    with pytest.raises(ManagerError, match="was not found"):
        await manager.add_source(Source(repo="busy-app/nonexistent"))

    assert manager.store.config.sources == []


@pytest.mark.asyncio
async def test_launching_goes_to_the_bar_for_a_bar_app(tmp_path: Path) -> None:
    bar = FakeBar([types.AppInfo(id="demo.app", name="Demo", version="1")])
    manager = manager_for(tmp_path, bar)
    (entry,), _ = await manager.entries()

    message = await manager.activate(entry)

    assert bar.done == ["launch demo.app"]
    assert message == "Launched Demo on the bar"


@pytest.mark.asyncio
async def test_quitting_with_an_external_app_selected_stops_that_app(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, FakeBar())
    manager.add_external("Slow", str(tmp_path), "sleep 30", "")
    (entry,), _ = await manager.entries()
    await manager.activate(entry)
    try:
        assert await manager.stop(entry) == "Stopped Slow"
    finally:
        manager.launcher.stop_all()


@pytest.mark.asyncio
async def test_quitting_with_a_bar_app_selected_quits_the_bar(tmp_path: Path) -> None:
    bar = FakeBar([types.AppInfo(id="demo.app", name="Demo", version="1")])
    manager = manager_for(tmp_path, bar)
    (entry,), _ = await manager.entries()

    await manager.stop(entry)

    assert bar.done == ["quit"]


@pytest.mark.asyncio
async def test_removing_an_external_app_forgets_it_and_leaves_its_files(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "mine"
    folder.mkdir()
    (folder / "keep.txt").write_text("x")
    manager = manager_for(tmp_path, FakeBar())
    manager.add_external("Mine", str(folder), "run", "")
    (entry,), _ = await manager.entries()

    message = await manager.remove(entry)

    assert manager.store.config.externals == []
    assert (folder / "keep.txt").exists()
    assert "nothing on disk was deleted" in message


@pytest.mark.asyncio
async def test_removing_a_bar_app_keeps_its_settings(tmp_path: Path) -> None:
    bar = FakeBar([types.AppInfo(id="demo.app", name="Demo", version="1")])
    manager = manager_for(tmp_path, bar)
    (entry,), _ = await manager.entries()

    message = await manager.remove(entry)

    assert bar.done == ["delete demo.app"]
    assert "settings are kept" in message


@pytest.mark.parametrize(
    "name, folder_exists, command, complaint",
    [
        ("", True, "run", "give it a name"),
        ("X", False, "run", "is not a folder"),
        ("X", True, "  ", "what command starts it"),
    ],
)
def test_an_external_app_that_could_not_run_is_refused_when_added(
    tmp_path: Path, name: str, folder_exists: bool, command: str, complaint: str
) -> None:
    manager = manager_for(tmp_path, None)
    path = str(tmp_path) if folder_exists else str(tmp_path / "missing")

    with pytest.raises(ManagerError, match=complaint):
        manager.add_external(name, path, command, "")

    assert manager.store.config.externals == []


def test_editing_an_external_app_keeps_its_identity(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, None)
    original = manager.add_external("Clock", str(tmp_path), "run", "old")

    edited = manager.edit_external(original, "Big Clock", str(tmp_path), "run2", "new")

    assert edited.slug == original.slug == "clock"
    assert [(a.name, a.command) for a in manager.store.config.externals] == [
        ("Big Clock", "run2")
    ]


# Programs from a catalog --------------------------------------------------------


PROGRAMS = Source(repo="busy-app/programs", kind="catalog")


def _with_catalog(tmp_path: Path, programs: dict, bar=None):
    net = CatalogNet(programs)
    manager = manager_for(tmp_path, bar)
    manager.github.fetch = net
    manager.programs.github = manager.github
    return net, manager


async def test_a_catalog_is_checked_before_it_is_kept(tmp_path: Path) -> None:
    _, manager = _with_catalog(tmp_path, {"clock": program("Clock")})

    added = await manager.add_source(Source(repo="busy-app/programs", kind="catalog"))

    assert added.title == "programs"
    assert manager.store.config.sources[0].kind == "catalog"
    assert manager.catalogs["busy-app/programs"].apps[0].slug == "clock"


async def test_an_empty_catalog_is_not_kept(tmp_path: Path) -> None:
    _, manager = _with_catalog(tmp_path, {})

    with pytest.raises(ManagerError, match="no programs in its apps/ folder"):
        await manager.add_source(Source(repo="busy-app/programs", kind="catalog"))

    assert manager.store.config.sources == []


async def test_installing_a_program_adds_it_to_the_list_with_a_command_that_follows_the_bar(
    tmp_path: Path,
) -> None:
    _, manager = _with_catalog(tmp_path, {"clock": program("Clock")})
    catalog = await manager.catalog(PROGRAMS)
    prepared = await manager.prepare_program(PROGRAMS, catalog, catalog.apps[0])

    installed = await manager.install_program(prepared, lambda line: None)

    assert installed.command == "{python} app.py --host {host}"
    assert installed.path == str(tmp_path / "programs" / "clock")
    entries, _ = await manager.entries()
    (entry,) = entries
    assert (entry.name, entry.origin, entry.status) == (
        "Clock",
        "busy-app/programs",
        "ready",
    )
    assert entry.description == "About Clock"


async def test_the_summary_tells_a_person_what_they_are_agreeing_to(
    tmp_path: Path,
) -> None:
    _, manager = _with_catalog(
        tmp_path,
        {"clock": {**program("Clock"), "requirements.txt": b"requests\n"}},
    )
    catalog = await manager.catalog(PROGRAMS)

    prepared = await manager.prepare_program(PROGRAMS, catalog, catalog.apps[0])

    summary = prepared.summary
    assert summary.startswith("Install Clock (3 file(s)")
    assert "needs the packages requests" in summary
    assert "runs on this computer with your permissions" in summary


async def test_an_update_keeps_the_command_and_the_settings_a_person_made(
    tmp_path: Path,
) -> None:
    net, manager = _with_catalog(tmp_path, {"clock": program("Clock")})
    catalog = await manager.catalog(PROGRAMS)
    first = await manager.install_program(
        await manager.prepare_program(PROGRAMS, catalog, catalog.apps[0]),
        lambda line: None,
    )
    manager.store.save_external(
        ExternalApp(
            first.slug,
            first.name,
            first.path,
            "{python} app.py --fast",
            env={"CITY": "Utrecht"},
        )
    )
    net.programs["clock"]["app.py"] = b"print('v2')\n"
    newer = await manager.catalog(PROGRAMS)

    prepared = await manager.prepare_program(PROGRAMS, newer, newer.apps[0])
    assert prepared.summary.startswith("Update Clock")
    updated = await manager.install_program(prepared, lambda line: None)

    assert updated.slug == first.slug, "the same entry, not a second one"
    assert updated.command == "{python} app.py --fast"
    assert updated.env == {"CITY": "Utrecht"}
    assert len(manager.store.config.externals) == 1


async def _installed(manager: Manager) -> list[Entry]:
    """
    What is on the bar or the computer, without what is merely on offer.
    """
    entries, _ = await manager.entries()
    return [entry for entry in entries if entry.kind != "available"]


async def test_a_program_the_catalog_has_changed_is_marked_as_out_of_date(
    tmp_path: Path,
) -> None:
    net, manager = _with_catalog(
        tmp_path, {"clock": program("Clock"), "weather": program("W")}
    )
    await manager.add_source(Source(repo="busy-app/programs", kind="catalog"))
    catalog = manager.catalogs["busy-app/programs"]
    clock = catalog.find("clock")
    assert clock is not None
    await manager.install_program(
        await manager.prepare_program(PROGRAMS, catalog, clock), lambda line: None
    )

    (before,) = await _installed(manager)
    assert before.update is False

    net.programs["clock"]["app.py"] = b"print('v2')\n"
    assert await manager.refresh_sources() == []
    (after,) = await _installed(manager)

    assert (after.update, after.status) == (True, "update")


async def test_a_neighbour_changing_does_not_mark_a_program(tmp_path: Path) -> None:
    net, manager = _with_catalog(
        tmp_path, {"clock": program("Clock"), "weather": program("W")}
    )
    await manager.add_source(Source(repo="busy-app/programs", kind="catalog"))
    catalog = manager.catalogs["busy-app/programs"]
    clock = catalog.find("clock")
    assert clock is not None
    await manager.install_program(
        await manager.prepare_program(PROGRAMS, catalog, clock), lambda line: None
    )

    net.programs["weather"]["app.py"] = b"print('new')\n"
    await manager.refresh_sources()
    (entry,) = await _installed(manager)

    assert entry.update is False


async def test_being_offline_when_checking_for_updates_is_a_sentence_not_a_crash(
    tmp_path: Path,
) -> None:
    _, manager = _with_catalog(tmp_path, {"clock": program("Clock")})
    manager.store.add_source(Source(repo="busy-app/programs", kind="catalog"))
    manager.github.fetch = lambda url, headers, limit: (_ for _ in ()).throw(
        ManagerError("cannot reach GitHub: offline")
    )

    problems = await manager.refresh_sources()

    assert problems == [
        "could not check busy-app/programs for updates: cannot reach GitHub: offline"
    ]


async def test_removing_an_installed_program_deletes_what_it_installed(
    tmp_path: Path,
) -> None:
    _, manager = _with_catalog(tmp_path, {"clock": program("Clock")})
    catalog = await manager.catalog(PROGRAMS)
    await manager.install_program(
        await manager.prepare_program(PROGRAMS, catalog, catalog.apps[0]),
        lambda line: None,
    )
    (entry,), _ = await manager.entries()

    message = await manager.remove(entry)

    assert "files it installed" in message
    assert not (tmp_path / "programs" / "clock").exists()
    assert manager.store.config.externals == []


async def test_forgetting_a_program_added_by_hand_still_leaves_its_files(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "mine"
    folder.mkdir()
    (folder / "work.txt").write_text("x")
    manager = manager_for(tmp_path, None)
    manager.add_external("Mine", str(folder), "run", "")
    (entry,), _ = await manager.entries()

    await manager.remove(entry)

    assert (folder / "work.txt").exists()
    assert manager.store.config.externals == []


async def test_the_page_of_a_program_is_its_own_repository_if_it_has_one(
    tmp_path: Path,
) -> None:
    net, manager = _with_catalog(
        tmp_path,
        {
            "clock": program("Clock"),
            "ported": {
                "app.py": b"x",
                "manifest.yaml": b"name: Ported\nrepo: https://github.com/someone/ported\n",
            },
        },
    )
    catalog = await manager.catalog(PROGRAMS)
    for slug in ("clock", "ported"):
        found = catalog.find(slug)
        assert found is not None
        await manager.install_program(
            await manager.prepare_program(PROGRAMS, catalog, found), lambda line: None
        )
    entries, _ = await manager.entries()
    pages = {e.name: manager.page_url(e) for e in entries}

    assert pages["Clock"] == "https://github.com/busy-app/programs/tree/main/apps/clock"
    assert pages["Ported"] == "https://github.com/someone/ported"


def test_a_program_added_by_hand_has_no_page(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, None)
    manager.add_external("Mine", str(tmp_path), "run", "")

    entry = manager._external_entry(manager.store.config.externals[0])

    assert manager.page_url(entry) is None


def test_the_values_a_person_fills_in_are_kept_and_an_empty_one_unsets(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, None)
    app = manager.add_external("X", str(tmp_path), "run", "", env="KEEP=1 DROP=2")

    updated = manager.set_env(app, {"CITY": "Utrecht", "DROP": ""})

    assert updated.env == {"KEEP": "1", "CITY": "Utrecht"}
    assert manager.store.config.externals[0].env == updated.env


def test_environment_is_typed_into_the_form_for_a_program_added_by_hand(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, None)

    app = manager.add_external("X", str(tmp_path), "run", "", env='CITY="New York"')

    assert app.env == {"CITY": "New York"}
    with pytest.raises(ManagerError, match="is not KEY=value"):
        manager.add_external("Y", str(tmp_path), "run", "", env="oops")


def test_editing_a_program_does_not_lose_the_interpreter_a_catalog_install_chose(
    tmp_path: Path,
) -> None:
    manager = manager_for(tmp_path, None)
    original = manager.add_external("X", str(tmp_path), "run", "")
    manager.store.save_external(
        ExternalApp(**{**original.__dict__, "python": "/venv/bin/python"})
    )
    stored = manager.store.config.externals[0]

    edited = manager.edit_external(stored, "X2", str(tmp_path), "run2", "")

    assert edited.python == "/venv/bin/python"


# Stopping the app on the bar ------------------------------------------------------


async def test_the_bar_is_asked_to_quit_before_anything_else(tmp_path: Path) -> None:
    bar = FakeBar([types.AppInfo(id="a.app", name="A", version="1")])
    manager = manager_for(tmp_path, bar)
    (entry,), _ = await manager.entries()

    assert await manager.stop(entry) == "Quit the app on the bar"
    assert bar.done == ["quit"]


async def test_a_bar_that_cannot_quit_is_left_alone_until_the_person_agrees(
    tmp_path: Path,
) -> None:
    bar = FakeBar([types.AppInfo(id="a.app", name="A", version="1")])
    bar.quit_answer = "unavailable"
    manager = manager_for(tmp_path, bar)
    (entry,), _ = await manager.entries()

    with pytest.raises(CannotQuitDirectly):
        await manager.stop(entry)

    assert bar.done == [], "the switch is not touched without being asked"


async def test_once_agreed_the_app_is_left_by_the_switch(tmp_path: Path) -> None:
    bar = FakeBar([types.AppInfo(id="a.app", name="A", version="1")])
    bar.quit_answer = "unavailable"
    manager = manager_for(tmp_path, bar)
    (entry,), _ = await manager.entries()

    message = await manager.stop(entry, by_switch=True)

    assert bar.done == ["switch"]
    assert "Apps menu" in message


async def test_nothing_running_is_said_and_the_switch_is_not_used(
    tmp_path: Path,
) -> None:
    bar = FakeBar([types.AppInfo(id="a.app", name="A", version="1")])
    bar.quit_answer = "none running"
    manager = manager_for(tmp_path, bar)
    (entry,), _ = await manager.entries()

    with pytest.raises(ManagerError, match="no app is running"):
        await manager.stop(entry)

    assert bar.done == []
