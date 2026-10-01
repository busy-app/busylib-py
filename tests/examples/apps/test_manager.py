from __future__ import annotations

from pathlib import Path

import pytest
from apps_support import MANIFEST, RELEASE, RELEASES, FakeBar, manager_for, tgz

from busylib import types
from examples.apps import package
from examples.apps.github import Reply
from examples.apps.model import Asset, ManagerError, Source, Version
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
    assert Store(tmp_path / "apps.json").load().sources[0].title == "Demo"


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
