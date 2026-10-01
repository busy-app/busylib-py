from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from examples.apps import store
from examples.apps.model import ExternalApp, ManagerError, Source
from examples.apps.store import Store, slugify


def test_what_was_added_is_there_after_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "apps.json"
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
    path = tmp_path / "apps.json"

    config = Store(path).load()

    assert (config.sources, config.externals) == ([], [])
    assert not path.exists()


def test_the_same_repository_is_not_a_source_twice(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.json")
    keeper.add_source(Source(repo="busy-app/demo"))

    with pytest.raises(ManagerError, match="already a source"):
        keeper.add_source(Source(repo="Busy-App/Demo"))


def test_one_repository_can_be_two_sources_in_different_folders(tmp_path: Path) -> None:
    """
    A monorepo holding several applications is one repository and several
    things to install.
    """
    keeper = Store(tmp_path / "apps.json")
    keeper.add_source(Source(repo="busy-app/apps", subdir="clock"))
    keeper.add_source(Source(repo="busy-app/apps", subdir="weather"))

    assert len(keeper.config.sources) == 2


def test_removing_a_source_keeps_the_others(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.json")
    keeper.add_source(Source(repo="a/one"))
    keeper.add_source(Source(repo="b/two"))

    keeper.remove_source("a/one")

    assert [s.repo for s in keeper.config.sources] == ["b/two"]
    assert [s.repo for s in Store(tmp_path / "apps.json").load().sources] == ["b/two"]


def test_saving_an_external_app_again_replaces_it(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.json")
    keeper.save_external(ExternalApp("clock", "Clock", "/a", "run"))

    keeper.save_external(ExternalApp("clock", "Clock 2", "/b", "run2"))

    assert [(a.name, a.path) for a in keeper.config.externals] == [("Clock 2", "/b")]


def test_two_apps_with_one_name_get_different_slugs(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "apps.json")
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
    path = tmp_path / "apps.json"
    path.write_text("{ this is not json")

    keeper = Store(path)
    config = keeper.load()

    assert (config.sources, config.externals) == ([], [])
    assert "could not be read" in keeper.warning
    assert (tmp_path / "apps.json.bad").read_text() == "{ this is not json"

    # And the manager carries on with a fresh file.
    keeper.add_source(Source(repo="a/b"))
    assert Store(path).load().sources == [Source(repo="a/b")]


def test_a_file_from_a_newer_manager_with_extra_fields_is_not_lost(
    tmp_path: Path,
) -> None:
    path = tmp_path / "apps.json"
    path.write_text(
        json.dumps({"version": 9, "sources": [{"repo": "a/b", "future": 1}]})
    )

    keeper = Store(path)
    keeper.load()

    assert keeper.config.sources == []
    assert (tmp_path / "apps.json.bad").exists()


def test_a_save_is_never_half_written(tmp_path: Path) -> None:
    keeper = Store(tmp_path / "deep" / "apps.json")
    keeper.add_source(Source(repo="a/b"))

    assert not list((tmp_path / "deep").glob("*.tmp"))
    assert json.loads((tmp_path / "deep" / "apps.json").read_text())["version"] == 1


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
