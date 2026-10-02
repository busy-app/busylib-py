"""
Adding a source by where it is, and finding what it offers in the list.

A person types `owner/name`. The manager works out what the repository is and
puts what it has in the list as not installed - and takes it off the list
when it is.
"""

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
from busylib import types
from examples.manager.github import Reply
from examples.manager.model import ManagerError, parse_repo

RAW = "https://raw.githubusercontent.com/busy-app/demo"


@pytest.mark.parametrize(
    "typed",
    [
        "busy-app/demo",
        "  busy-app/demo  ",
        "https://github.com/busy-app/demo",
        "https://github.com/busy-app/demo/",
        "https://github.com/busy-app/demo.git",
        "https://github.com/busy-app/demo/tree/main/src?x=1",
        "http://www.github.com/busy-app/demo",
        "git@github.com:busy-app/demo.git",
        "github.com/busy-app/demo",
    ],
)
def test_a_repository_is_recognised_however_it_was_pasted(typed: str) -> None:
    assert parse_repo(typed) == "busy-app/demo"


@pytest.mark.parametrize(
    "typed", ["", "demo", "busy-app", "https://example.com/busy-app/demo", "a/../b"]
)
def test_what_is_not_a_repository_is_said_so(typed: str) -> None:
    with pytest.raises(ManagerError, match="owner/name"):
        parse_repo(typed)


# What a release-based app's repository answers.
APP = {
    RELEASES: [RELEASE],
    f"{RAW}/v1.2.0/src/appmeta/manifest.json": Reply(200, MANIFEST),
}


async def test_a_catalog_is_recognised_and_its_programs_are_on_offer(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(
        tmp_path, {"clock": program("Clock"), "weather": program("Weather")}
    )

    source = await manager.add_repo("busy-app/programs")

    assert (source.kind, source.title) == ("catalog", "programs")
    entries, _ = await manager.entries()
    assert [(e.name, e.status, e.where) for e in entries] == [
        ("Clock", "not installed", "computer"),
        ("Weather", "not installed", "computer"),
    ]


async def test_an_app_with_releases_is_recognised_and_offered(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, FakeBar(), APP)

    source = await manager.add_repo("https://github.com/busy-app/demo")

    assert (source.kind, source.mode, source.title) == ("app", "release", "Demo")
    (entry,), _ = await manager.entries()
    assert (entry.name, entry.version, entry.status, entry.where) == (
        "Demo",
        "1.2.0",
        "not installed",
        "bar",
    )


async def test_an_app_with_no_release_is_built_from_its_source(tmp_path: Path) -> None:
    routes = {
        "https://api.github.com/repos/busy-app/demo": {"default_branch": "main"},
        "https://api.github.com/repos/busy-app/demo/tags?per_page=30": [],
        f"{RAW}/main/src/appmeta/manifest.json": Reply(200, MANIFEST),
    }
    manager = manager_for(tmp_path, FakeBar(), routes)

    source = await manager.add_repo("busy-app/demo")

    assert (source.kind, source.mode) == ("app", "build")


async def test_a_repository_with_nothing_to_install_says_what_it_looked_for(
    tmp_path: Path,
) -> None:
    routes = {
        "https://api.github.com/repos/busy-app/docs": {"default_branch": "main"},
        "https://api.github.com/repos/busy-app/docs/tags?per_page=30": [],
    }
    manager = manager_for(tmp_path, FakeBar(), routes)

    with pytest.raises(ManagerError, match="nothing to install"):
        await manager.add_repo("busy-app/docs")
    assert manager.store.config.sources == []


async def test_a_repository_that_is_not_there_says_so(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, FakeBar())

    with pytest.raises(ManagerError, match="not found"):
        await manager.add_repo("busy-app/typo")


async def test_the_same_repository_is_not_added_twice(tmp_path: Path) -> None:
    manager = manager_for(tmp_path, FakeBar(), APP)
    await manager.add_repo("busy-app/demo")

    with pytest.raises(ManagerError, match="already a source"):
        await manager.add_repo("https://github.com/Busy-App/Demo")


async def test_what_is_on_offer_is_known_before_the_network_answers(
    tmp_path: Path,
) -> None:
    """
    The offers are in the database, so a fresh start - and a start with no
    network at all - already shows what the sources had.
    """
    manager = manager_for(tmp_path, FakeBar(), APP)
    await manager.add_repo("busy-app/demo")

    again = manager_for(tmp_path, FakeBar())
    again.store.load()

    (entry,), _ = await again.entries()
    assert (entry.name, entry.status) == ("Demo", "not installed")


async def test_an_app_on_the_bar_is_no_longer_on_offer(tmp_path: Path) -> None:
    bar = FakeBar([types.AppInfo(id="demo.app", name="Demo", version="1.2.0")])
    manager = manager_for(tmp_path, bar, APP)
    await manager.add_repo("busy-app/demo")

    entries, _ = await manager.entries()

    assert [(e.kind, e.status) for e in entries] == [("bar", "installed")]


async def test_an_installed_program_is_no_longer_on_offer(tmp_path: Path) -> None:
    _, manager = manager_with_catalog(
        tmp_path, {"clock": program("Clock"), "weather": program("Weather")}
    )
    source = await manager.add_repo("busy-app/programs")
    catalog = manager.catalogs[source.repo]
    clock = catalog.find("clock")
    assert clock is not None
    await manager.install_program(
        await manager.prepare_program(source, catalog, clock), lambda line: None
    )

    entries, _ = await manager.entries()

    assert [(e.name, e.status) for e in entries] == [
        ("Clock", "ready"),
        ("Weather", "not installed"),
    ]


async def test_installing_what_was_on_offer_takes_it_off_the_offer(
    tmp_path: Path,
) -> None:
    """
    Even when the repository's manifest could not be read ahead of time, so
    nothing said which app on the bar it would become.
    """
    routes = {
        RELEASES: [RELEASE],
        "https://dl/demo.tgz": Reply(
            200, tgz({"appmeta/manifest.json": MANIFEST, "main.js": b"x"})
        ),
    }
    bar = FakeBar()
    manager = manager_for(tmp_path, bar, routes)
    source = await manager.add_repo("busy-app/demo")
    (offered,), _ = await manager.entries()
    assert (offered.status, offered.name) == ("not installed", "busy-app/demo")

    versions = await manager.versions(source)
    prepared = await manager.prepare(source, versions[0], lambda line: None)
    await manager.commit(prepared)

    entries, _ = await manager.entries()
    assert [(e.kind, e.name) for e in entries] == [("bar", "Demo")]


async def test_refreshing_updates_what_is_on_offer(tmp_path: Path) -> None:
    net, manager = manager_with_catalog(tmp_path, {"clock": program("Clock")})
    await manager.add_repo("busy-app/programs")

    net.programs["weather"] = program("Weather")
    assert await manager.refresh_sources() == []

    entries, _ = await manager.entries()
    assert [e.name for e in entries] == ["Clock", "Weather"]


async def test_forgetting_a_source_takes_its_offers_off_the_list(
    tmp_path: Path,
) -> None:
    _, manager = manager_with_catalog(tmp_path, {"clock": program("Clock")})
    source = await manager.add_repo("busy-app/programs")

    manager.forget_source(source)

    assert (await manager.entries())[0] == []
