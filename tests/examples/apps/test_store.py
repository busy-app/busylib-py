from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from examples.apps import store
from examples.apps.model import ExternalApp, ManagerError, Offer, Source
from examples.apps.store import Store, slugify


def test_what_was_added_is_there_after_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "apps.db"
    first = Store(path)
    first.add_source(
        Source(repo="busy-app/demo", mode="build", subdir="apps/x", title="Demo")
    )
    first.save_external(
        ExternalApp("clock", "Clock", "/tmp", "python clock.py", "A clock")
    )

    second = Store(path)
    config = second.load()

    assert config.sources == [
        Source(repo="busy-app/demo", mode="build", subdir="apps/x", title="Demo")
    ]
    assert config.externals[0].command == "python clock.py"


def test_a_first_run_has_nothing_and_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "apps.db"

    config = Store(path).load()

    assert (config.sources, config.externals) == ([], [])
    assert not path.exists()


def test_the_same_repository_is_not_a_source_twice(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.db")
    keeper.add_source(Source(repo="busy-app/demo"))

    with pytest.raises(ManagerError, match="already a source"):
        keeper.add_source(Source(repo="Busy-App/Demo"))


def test_one_repository_can_be_two_sources_in_different_folders(tmp_path: Path) -> None:
    """
    A monorepo holding several applications is one repository and several
    things to install.
    """
    keeper = Store(tmp_path / "apps.db")
    keeper.add_source(Source(repo="busy-app/apps", subdir="clock"))
    keeper.add_source(Source(repo="busy-app/apps", subdir="weather"))

    assert len(keeper.config.sources) == 2


def test_removing_a_source_keeps_the_others(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.db")
    keeper.add_source(Source(repo="a/one"))
    keeper.add_source(Source(repo="b/two"))

    keeper.remove_source("a/one")

    assert [s.repo for s in keeper.config.sources] == ["b/two"]
    assert [s.repo for s in Store(tmp_path / "apps.db").load().sources] == ["b/two"]


def test_saving_an_external_app_again_replaces_it(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.db")
    keeper.save_external(ExternalApp("clock", "Clock", "/a", "run"))

    keeper.save_external(ExternalApp("clock", "Clock 2", "/b", "run2"))

    assert [(a.name, a.path) for a in keeper.config.externals] == [("Clock 2", "/b")]


def test_two_apps_with_one_name_get_different_slugs(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.db")
    keeper.save_external(
        ExternalApp(keeper.unused_slug("My Clock"), "My Clock", "/", "x")
    )

    assert keeper.unused_slug("My Clock") == "my-clock-2"


@pytest.mark.parametrize(
    "name, slug",
    [
        ("My Clock", "my-clock"),
        ("  ~~weird!!  ", "weird"),
        ("Часы", "app"),
        ("", "app"),
    ],
)
def test_a_slug_is_plain_ascii(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_a_file_that_cannot_be_read_is_set_aside_not_overwritten(
    tmp_path: Path,
) -> None:
    """
    It may be the only copy of something a person typed.
    """
    path = tmp_path / "apps.db"
    path.write_text("this is not a database")

    keeper = Store(path)
    config = keeper.load()

    assert (config.sources, config.externals) == ([], [])
    assert "could not be read" in keeper.warning
    assert (tmp_path / "apps.db.bad").read_text() == "this is not a database"

    # And the manager carries on with a fresh file.
    keeper.add_source(Source(repo="a/b"))
    assert Store(path).load().sources == [Source(repo="a/b")]


def test_a_database_from_a_newer_manager_is_set_aside_not_misread(
    tmp_path: Path,
) -> None:
    path = tmp_path / "apps.db"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version = 99")

    keeper = Store(path)
    keeper.load()

    assert keeper.config.sources == []
    assert "newer manager" in keeper.warning
    assert (tmp_path / "apps.db.bad").exists()


def test_what_the_json_file_held_is_taken_in_once(tmp_path: Path) -> None:
    """
    Before it had a database the manager kept one JSON file. A person who
    upgrades must find their sources where they left them - and the old
    file is kept, since it is still a copy of what they typed.
    """
    legacy = tmp_path / "apps.json"
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [{"repo": "a/b", "title": "Mine"}],
                "externals": [
                    {
                        "slug": "clock",
                        "name": "Clock",
                        "path": "/x",
                        "command": "run",
                        "env": {"CITY": "Utrecht"},
                    }
                ],
            }
        )
    )

    first = Store(tmp_path / "apps.db").load()

    assert [s.title for s in first.sources] == ["Mine"]
    assert first.externals[0].env == {"CITY": "Utrecht"}
    assert not legacy.exists()
    assert (tmp_path / "apps.json.imported").exists()
    # Opened again, nothing is taken in twice.
    assert len(Store(tmp_path / "apps.db").load().sources) == 1


def test_the_first_run_creates_the_database_only_when_something_is_kept(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deep" / "apps.db"
    keeper = Store(path)
    keeper.load()
    assert not path.exists()

    keeper.add_source(Source(repo="a/b"))

    assert path.exists()


def test_what_a_source_offered_is_there_after_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "apps.db"
    keeper = Store(path)
    keeper.add_source(Source(repo="a/b"))
    keeper.add_source(Source(repo="c/d", kind="catalog"))
    keeper.set_offers("c/d", "", [Offer("c/d", "", "clock", "Clock", description="x")])
    keeper.set_offers("a/b", "", [Offer("a/b", "", "", "Demo", "1.0", app_id="demo")])

    offers = Store(path).offers()

    # In the order the sources were added.
    assert [(o.repo, o.name, o.app_id) for o in offers] == [
        ("a/b", "Demo", "demo"),
        ("c/d", "Clock", ""),
    ]


def test_seeing_a_source_again_replaces_what_it_offered(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.db")
    keeper.add_source(Source(repo="c/d", kind="catalog"))
    keeper.set_offers(
        "c/d", "", [Offer("c/d", "", "a", "A"), Offer("c/d", "", "b", "B")]
    )

    keeper.set_offers("c/d", "", [Offer("c/d", "", "b", "B 2")])

    assert [o.name for o in keeper.offers()] == ["B 2"]


def test_forgetting_a_source_forgets_what_it_offered(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.db")
    keeper.add_source(Source(repo="a/b"))
    keeper.set_offers("a/b", "", [Offer("a/b", "", "", "Demo")])

    keeper.remove_source("a/b")

    assert keeper.offers() == []


@pytest.mark.parametrize(
    "platform, env, expected",
    [
        ("win32", {"APPDATA": "C:/Users/me/AppData/Roaming"}, "busy-apps"),
        ("darwin", {}, "Library/Application Support/busy-apps"),
        ("linux", {"XDG_CONFIG_HOME": "/xdg"}, "/xdg/busy-apps"),
        ("linux", {}, ".config/busy-apps"),
    ],
)
def test_each_system_keeps_it_where_that_system_keeps_such_things(
    monkeypatch: pytest.MonkeyPatch, platform: str, env: dict[str, str], expected: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    for key in ("APPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert store.default_config_dir().as_posix().endswith(expected)
