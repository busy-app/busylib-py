"""
Apps from a folder, builds by commit, and the builds that are kept.

A package built from source is kept on this computer and is one of the
versions of its app from then on: in the list among the releases, in the order
things happened, and installable without building again.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from manager_support import MANIFEST, RELEASE, RELEASES, FakeBar, manager_for, tgz

from examples.manager import package
from examples.manager.github import Reply
from examples.manager.manager import Manager
from examples.manager.model import Build, ManagerError, Source, Version

SHA = "0123456789abcdef0123456789abcdef01234567"
COMMITS = "https://api.github.com/repos/busy-app/demo/commits?per_page=30"
ARCHIVE = f"https://codeload.github.com/busy-app/demo/tar.gz/{SHA}"


class Builder:
    """
    A package manager that builds the app, and remembers being asked to.
    """

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        if argv[1:] == ["--version"]:
            return 0, "v25.2.1\n"
        self.commands.append(argv[1:])
        if argv[1:] == ["run", "build"]:
            out = cwd / "dist/demo.app/appmeta"
            out.mkdir(parents=True)
            (out / "manifest.json").write_bytes(MANIFEST)
            (cwd / "dist/demo.app/main.js").write_bytes(b"built")
        return 0, ""


@pytest.fixture(autouse=True)
def node_is_there(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(package.shutil, "which", lambda name: f"/bin/{name}")


SOURCE_TREE = {
    "demo-abc/src/appmeta/manifest.json": MANIFEST,
    "demo-abc/pnpm-lock.yaml": b"",
}


def _manager(tmp_path: Path, routes: dict | None = None, builder=None) -> Manager:
    return manager_for(tmp_path, FakeBar(), routes or {}, run=builder or Builder())


def _project(tmp_path: Path, name: str = "my-app") -> Path:
    """
    An app's source folder, with a manifest and a lockfile.
    """
    folder = tmp_path / name
    (folder / "src/appmeta").mkdir(parents=True)
    (folder / "src/appmeta/manifest.json").write_bytes(MANIFEST)
    (folder / "pnpm-lock.yaml").write_text("")
    return folder


# Adding a folder ------------------------------------------------------------------


async def test_a_folder_is_added_by_its_path_and_offered_as_not_installed(
    tmp_path: Path,
) -> None:
    folder = _project(tmp_path)
    manager = _manager(tmp_path)

    source = await manager.add_repo(str(folder))

    assert (source.local, source.mode, source.title) == (True, "build", "Demo")
    (entry,), _ = await manager.entries()
    assert (entry.name, entry.version, entry.status, entry.where) == (
        "Demo",
        "1.2.0",
        "not installed",
        "bar",
    )
    assert entry.came_from == source.origin and str(folder).endswith(
        entry.came_from[1:]
    )


async def test_a_folder_is_remembered_with_everything_about_it(tmp_path: Path) -> None:
    folder = _project(tmp_path)
    manager = _manager(tmp_path)
    await manager.add_repo(str(folder))

    again = _manager(tmp_path)
    again.store.load()

    (source,) = again.store.config.sources
    assert (source.local, source.repo) == (True, str(folder.resolve()))


async def test_a_folder_under_home_is_written_with_a_tilde(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    source = Source(repo=str(tmp_path / "work" / "app"), local=True)

    assert source.origin == "~/work/app"
    assert Source(repo="/elsewhere/app", local=True).origin == "/elsewhere/app"
    assert Source(repo="busy-app/demo").origin == "busy-app/demo"


async def test_the_same_folder_is_not_a_source_twice(tmp_path: Path) -> None:
    folder = _project(tmp_path)
    manager = _manager(tmp_path)
    await manager.add_repo(str(folder))

    with pytest.raises(ManagerError, match="already a source"):
        await manager.add_repo(str(folder) + "/")


async def test_a_folder_with_no_app_in_it_says_what_was_looked_for(
    tmp_path: Path,
) -> None:
    (tmp_path / "empty").mkdir()
    manager = _manager(tmp_path)

    with pytest.raises(ManagerError, match="no manifest"):
        await manager.add_repo(str(tmp_path / "empty"))
    assert manager.store.config.sources == []


async def test_a_path_that_is_not_there_says_so(tmp_path: Path) -> None:
    with pytest.raises(ManagerError, match="is not a folder"):
        await _manager(tmp_path).add_repo(str(tmp_path / "nope"))


# Building -------------------------------------------------------------------------


async def test_the_working_copy_is_built_on_a_copy_and_the_build_kept(
    tmp_path: Path,
) -> None:
    folder = _project(tmp_path)
    builder = Builder()
    manager = _manager(tmp_path, builder=builder)
    source = await manager.add_repo(str(folder))
    (copy,) = [v for v in await manager.versions(source) if v.kind == "local"]

    prepared = await manager.prepare(source, copy, lambda line: None)

    assert builder.commands == [["install", "--frozen-lockfile"], ["run", "build"]]
    assert prepared.package.manifest.id == "demo.app"
    assert not (folder / "dist").exists(), "nothing was left in the project"
    assert not (folder / "node_modules").exists()
    (build,) = manager.store.builds(source.repo)
    assert Path(build.path).parent == tmp_path / "builds" / Path(build.path).parent.name
    assert Path(build.path).read_bytes() == prepared.package.data
    assert (build.app_id, build.version, build.ref) == (
        "demo.app",
        "1.2.0",
        "working copy",
    )


async def test_an_app_that_is_already_built_is_packaged_without_building(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "ready"
    (folder / "appmeta").mkdir(parents=True)
    (folder / "appmeta/manifest.json").write_bytes(MANIFEST)
    (folder / "main.js").write_bytes(b"x")
    builder = Builder()
    manager = _manager(tmp_path, builder=builder)
    source = await manager.add_repo(str(folder))
    said: list[str] = []

    prepared = await manager.prepare(
        source, Version("working-copy", "Working copy", "local"), said.append
    )

    assert builder.commands == []
    assert prepared.package.manifest.id == "demo.app"
    assert any("no build step" in line for line in said)


async def test_a_commit_of_a_github_source_is_built_and_kept(tmp_path: Path) -> None:
    builder = Builder()
    manager = _manager(
        tmp_path, {ARCHIVE: Reply(200, tgz(SOURCE_TREE))}, builder=builder
    )
    source = Source(repo="busy-app/demo", mode="build")
    commit = Version(SHA, f"{SHA[:7]} Fix the thing", "commit")

    prepared = await manager.prepare(source, commit, lambda line: None)

    assert builder.commands == [["install", "--frozen-lockfile"], ["run", "build"]]
    (build,) = manager.store.builds("busy-app/demo")
    assert build.ref == SHA and build.label == commit.label
    assert Path(build.path).read_bytes() == prepared.package.data
    assert build.path.endswith(f"-{SHA[:7]}.tgz")


async def test_a_kept_build_is_installed_without_building(tmp_path: Path) -> None:
    builder = Builder()
    manager = _manager(
        tmp_path, {ARCHIVE: Reply(200, tgz(SOURCE_TREE))}, builder=builder
    )
    source = Source(repo="busy-app/demo", mode="build")
    await manager.prepare(
        source, Version(SHA, f"{SHA[:7]} Fix", "commit"), lambda line: None
    )
    builder.commands.clear()
    (kept,) = [v for v in await manager.versions(source) if v.kind == "build"]

    prepared = await manager.prepare(source, kept, lambda line: None)

    assert builder.commands == [], "nothing was built"
    assert prepared.package.manifest.id == "demo.app"
    assert manager.bar is not None and prepared.staged.staged.id == "demo.app"


async def test_a_kept_build_that_has_gone_from_disk_says_so(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    source = Source(repo="busy-app/demo")
    manager.store.add_source(source)
    gone = Version("build:x.tgz", "x", "build", artifact=str(tmp_path / "x.tgz"))

    with pytest.raises(ManagerError, match="kept build cannot be read"):
        await manager.prepare(source, gone, lambda line: None)


async def test_a_build_that_fails_keeps_nothing(tmp_path: Path) -> None:
    def broken(argv: list[str], cwd: Path) -> tuple[int, str]:
        return (0, "v25.2.1\n") if argv[1:] == ["--version"] else (1, "boom")

    manager = _manager(tmp_path, {ARCHIVE: Reply(200, tgz(SOURCE_TREE))}, broken)
    source = Source(repo="busy-app/demo", mode="build")

    with pytest.raises(ManagerError, match="failed"):
        await manager.prepare(source, Version(SHA, "x", "commit"), lambda line: None)

    assert manager.store.builds("busy-app/demo") == []


async def test_not_being_able_to_keep_a_build_does_not_fail_the_install(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path, {ARCHIVE: Reply(200, tgz(SOURCE_TREE))})
    (tmp_path / "builds").write_text("a file where the folder should go")
    said: list[str] = []

    prepared = await manager.prepare(
        Source(repo="busy-app/demo", mode="build"),
        Version(SHA, "x", "commit"),
        said.append,
    )

    assert prepared.package.manifest.id == "demo.app"
    assert any("could not keep the build" in line for line in said)


# The list of versions -------------------------------------------------------------


def _kept(tmp_path: Path, built_at: str, version: str = "1.3.0") -> Build:
    path = tmp_path / f"{built_at}.tgz"
    path.write_bytes(tgz({"appmeta/manifest.json": MANIFEST}))
    return Build(
        "busy-app/demo", "", SHA, f"{SHA[:7]} x", "demo.app", "Demo", version, built_at,
        str(path),
    )  # fmt: skip


async def test_releases_and_builds_are_one_list_in_the_order_things_happened(
    tmp_path: Path,
) -> None:
    release = {**RELEASE, "published_at": "2026-09-30T00:00:00Z"}
    older = {**RELEASE, "tag_name": "v1.1.0", "published_at": "2026-09-01T00:00:00Z"}
    manager = _manager(tmp_path, {RELEASES: [release, older]})
    source = Source(repo="busy-app/demo")
    manager.store.add_source(source)
    manager.store.add_build(_kept(tmp_path, "2026-09-15T12:00:00+00:00", "1.1.5"))
    manager.store.add_build(_kept(tmp_path, "2026-10-02T08:00:00+00:00", "1.3.0"))

    versions = await manager.versions(source)

    assert [(v.kind, v.ref[:8]) for v in versions] == [
        ("build", "build:20"),
        ("release", "v1.2.0"),
        ("build", "build:20"),
        ("release", "v1.1.0"),
    ]
    assert [v.published[:10] for v in versions] == [
        "2026-10-02",
        "2026-09-30",
        "2026-09-15",
        "2026-09-01",
    ]


async def test_a_build_and_a_release_in_different_time_zones_are_ordered_by_the_moment(
    tmp_path: Path,
) -> None:
    release = {**RELEASE, "published_at": "2026-09-30T23:00:00Z"}
    manager = _manager(tmp_path, {RELEASES: [release]})
    source = Source(repo="busy-app/demo")
    manager.store.add_source(source)
    # 02:00 on the 1st at +05:00 is 21:00 on the 30th in UTC: earlier.
    manager.store.add_build(_kept(tmp_path, "2026-10-01T02:00:00+05:00"))

    versions = await manager.versions(source)

    assert [v.kind for v in versions] == ["release", "build"]


async def test_the_heads_without_a_date_stay_above_the_dated_ones(
    tmp_path: Path,
) -> None:
    routes = {
        "https://api.github.com/repos/busy-app/demo": {"default_branch": "main"},
        "https://api.github.com/repos/busy-app/demo/tags?per_page=30": [{"name": "v1"}],
    }
    manager = _manager(tmp_path, routes)
    source = Source(repo="busy-app/demo", mode="build")
    manager.store.add_source(source)
    manager.store.add_build(_kept(tmp_path, "2026-10-02T08:00:00+00:00"))

    versions = await manager.versions(source)

    assert [v.kind for v in versions] == ["branch", "tag", "build"]


async def test_a_source_with_no_release_still_lists_what_was_built_from_it(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path, {RELEASES: []})
    source = Source(repo="busy-app/demo")
    manager.store.add_source(source)
    manager.store.add_build(_kept(tmp_path, "2026-10-02T08:00:00+00:00"))

    versions = await manager.versions(source)

    assert [v.kind for v in versions] == ["build"]


async def test_a_source_with_nothing_at_all_says_so(tmp_path: Path) -> None:
    manager = _manager(tmp_path, {RELEASES: []})

    with pytest.raises(ManagerError, match="no release"):
        await manager.versions(Source(repo="busy-app/demo"))


async def test_a_folders_versions_are_its_working_copy_and_its_builds(
    tmp_path: Path,
) -> None:
    folder = _project(tmp_path)
    manager = _manager(tmp_path)
    source = await manager.add_repo(str(folder))
    manager.store.add_build(
        Build(source.repo, "", "working copy", "Working copy", "demo.app", "Demo",
              "1.2.0", "2026-10-02T08:00:00+00:00", str(tmp_path / "x.tgz"))
    )  # fmt: skip

    versions = await manager.versions(source)

    assert [v.kind for v in versions] == ["local", "build"]
    assert versions[0].label.startswith("Working copy")


async def test_the_commits_of_a_github_source_are_offered_to_build(
    tmp_path: Path,
) -> None:
    listing = [
        {
            "sha": SHA,
            "commit": {
                "message": "Fix the thing\n\nLong text",
                "committer": {"date": "2026-10-01T10:00:00Z"},
                "author": {"name": "Ann"},
            },
        },
        {"sha": "f" * 40, "commit": {"message": "Older"}},
    ]
    manager = _manager(tmp_path, {COMMITS: listing})

    found = await manager.commits(Source(repo="busy-app/demo"))

    assert [(v.ref, v.label, v.kind) for v in found] == [
        (SHA, f"{SHA[:7]} Fix the thing", "commit"),
        ("f" * 40, f"{'f' * 7} Older", "commit"),
    ]
    assert (found[0].published, found[0].note) == ("2026-10-01T10:00:00Z", "Ann")


async def test_a_repository_with_no_commits_to_list_says_so(tmp_path: Path) -> None:
    manager = _manager(tmp_path, {COMMITS: []})

    with pytest.raises(ManagerError, match="no commits"):
        await manager.commits(Source(repo="busy-app/demo"))


async def test_forgetting_a_source_deletes_the_builds_kept_from_it(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    source = Source(repo="busy-app/demo")
    manager.store.add_source(source)
    build = _kept(tmp_path, "2026-10-02T08:00:00+00:00")
    manager.store.add_build(build)
    assert Path(build.path).exists()

    manager.forget_source(source)

    assert not Path(build.path).exists()
    assert manager.store.builds("busy-app/demo") == []


async def test_a_database_from_before_folders_gains_the_column(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "apps.db"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE sources (repo TEXT NOT NULL COLLATE NOCASE, subdir TEXT NOT NULL"
            " DEFAULT '', mode TEXT NOT NULL DEFAULT 'release', manifest TEXT NOT NULL"
            " DEFAULT '', asset TEXT NOT NULL DEFAULT '*.tgz', title TEXT NOT NULL DEFAULT"
            " '', kind TEXT NOT NULL DEFAULT 'app', branch TEXT NOT NULL DEFAULT '',"
            " position INTEGER NOT NULL, PRIMARY KEY (repo, subdir));"
            "INSERT INTO sources (repo, position) VALUES ('a/b', 1);"
            "PRAGMA user_version = 1;"
        )

    manager = manager_for(tmp_path, None)
    manager.store.load()

    assert [(s.repo, s.local) for s in manager.store.config.sources] == [("a/b", False)]
    assert json.dumps(manager.store.config.sources[0].__dict__)  # a plain Source
