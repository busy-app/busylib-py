from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import pytest

from examples.manager import package
from examples.manager.model import ManagerError

MANIFEST = b'{"id": "demo.app", "name": "Demo", "version": "1.2.0", "author": "Me"}'


def _tar(members: dict[str, bytes], *, compress: bool = True) -> bytes:
    """
    An archive holding exactly the named files.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz" if compress else "w") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _names(data: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        return sorted(m.name for m in tar if m.isfile())


def test_a_package_with_its_own_folder_is_kept_in_that_shape() -> None:
    data = _tar(
        {
            "demo.app/appmeta/manifest.json": MANIFEST,
            "demo.app/scripts/main.js": b"run()",
        }
    )

    result = package.normalize_package(data)

    assert result.manifest.id == "demo.app"
    assert result.manifest.version == "1.2.0"
    assert _names(result.data) == [
        "demo.app/appmeta/manifest.json",
        "demo.app/scripts/main.js",
    ]


def test_a_package_without_a_folder_gets_one_named_by_its_id() -> None:
    """
    The bar's installer looks at the first level for a folder; files lying
    loose in the archive's root would never be found.
    """
    data = _tar({"appmeta/manifest.json": MANIFEST, "scripts/main.js": b"run()"})

    result = package.normalize_package(data)

    assert _names(result.data) == [
        "demo.app/appmeta/manifest.json",
        "demo.app/scripts/main.js",
    ]


def test_a_folder_named_unlike_the_app_is_renamed_to_it() -> None:
    """
    GitHub names a source archive's folder after the commit; the bar does
    not care, but a person looking at the package should find the id.
    """
    data = _tar({"owner-repo-1a2b3c/appmeta/manifest.json": MANIFEST})

    assert _names(package.normalize_package(data).data) == [
        "demo.app/appmeta/manifest.json"
    ]


def test_packing_is_the_same_bytes_every_time() -> None:
    """
    So "did the package change" can be answered with a hash.
    """
    data = _tar({"appmeta/manifest.json": MANIFEST, "a.js": b"1", "b.js": b"2"})

    first = package.normalize_package(data).data
    second = package.normalize_package(
        _tar({"b.js": b"2", "a.js": b"1", "appmeta/manifest.json": MANIFEST})
    ).data

    assert first == second


def test_what_an_operating_system_leaves_behind_does_not_travel() -> None:
    data = _tar(
        {
            "appmeta/manifest.json": MANIFEST,
            ".DS_Store": b"x",
            "._manifest.json": b"x",
            "__MACOSX/appmeta/._manifest.json": b"x",
            "scripts/main.js": b"run()",
        }
    )

    assert _names(package.normalize_package(data).data) == [
        "demo.app/appmeta/manifest.json",
        "demo.app/scripts/main.js",
    ]


def test_a_plain_tar_is_accepted_as_well_as_a_tgz() -> None:
    data = _tar({"appmeta/manifest.json": MANIFEST}, compress=False)

    assert package.normalize_package(data).manifest.id == "demo.app"


@pytest.mark.parametrize(
    "name",
    ["../escape/appmeta/manifest.json", "/abs/appmeta/manifest.json", "a/../../b"],
)
def test_a_path_that_leaves_its_folder_is_refused(name: str) -> None:
    with pytest.raises(ManagerError, match="unsafe path"):
        package.normalize_package(_tar({name: MANIFEST}))


def test_a_link_inside_a_package_is_refused() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        manifest = tarfile.TarInfo("appmeta/manifest.json")
        manifest.size = len(MANIFEST)
        tar.addfile(manifest, io.BytesIO(MANIFEST))
        link = tarfile.TarInfo("appmeta/secret")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)

    with pytest.raises(ManagerError, match="link or device"):
        package.normalize_package(buffer.getvalue())


def test_something_that_is_not_an_archive_says_so() -> None:
    with pytest.raises(ManagerError, match="not a tar or tgz"):
        package.normalize_package(b"<html>rate limited</html>")


def test_an_archive_with_no_manifest_is_not_an_application() -> None:
    with pytest.raises(ManagerError, match="no appmeta/manifest.json"):
        package.normalize_package(_tar({"scripts/main.js": b"run()"}))


def test_two_applications_in_one_archive_are_ambiguous() -> None:
    """
    The bar takes the first folder that loads, so which one would land is
    down to directory order - not something to leave to chance.
    """
    other = MANIFEST.replace(b"demo.app", b"other.app")
    data = _tar({"a/appmeta/manifest.json": MANIFEST, "b/appmeta/manifest.json": other})

    with pytest.raises(ManagerError, match="more than one application"):
        package.normalize_package(data)


@pytest.mark.parametrize(
    "manifest, complaint",
    [
        (b"not json", "not valid JSON"),
        (b'{"id": "x"}', "no name, version"),
        (b'{"id": "has space", "name": "n", "version": "1"}', "not an application id"),
        (b'{"id": "' + b"a" * 40 + b'", "name": "n", "version": "1"}', "at most 32"),
        (b"[1, 2]", "not a JSON object"),
    ],
)
def test_a_manifest_the_bar_would_refuse_is_refused_here_first(
    manifest: bytes, complaint: str
) -> None:
    with pytest.raises(ManagerError, match=complaint):
        package.normalize_package(_tar({"appmeta/manifest.json": manifest}))


def test_a_download_larger_than_the_bar_takes_is_refused_before_reading_it() -> None:
    from examples.manager.model import MAX_PACKAGE_BYTES

    with pytest.raises(ManagerError, match="larger than the bar accepts"):
        package.normalize_package(b"x" * (MAX_PACKAGE_BYTES + 1))


def test_a_built_folder_is_packed_under_its_id(tmp_path: Path) -> None:
    app = tmp_path / "built"
    (app / "appmeta").mkdir(parents=True)
    (app / "appmeta/manifest.json").write_bytes(MANIFEST)
    (app / "scripts").mkdir()
    (app / "scripts/main.js").write_bytes(b"run()")
    (app / ".DS_Store").write_bytes(b"x")

    result = package.pack_directory(app)

    assert _names(result.data) == [
        "demo.app/appmeta/manifest.json",
        "demo.app/scripts/main.js",
    ]


def test_a_folder_that_is_not_built_yet_says_what_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ManagerError, match="has no appmeta/manifest.json"):
        package.pack_directory(tmp_path)


def test_the_repack_is_a_valid_gzip() -> None:
    data = package.normalize_package(_tar({"appmeta/manifest.json": MANIFEST})).data

    assert gzip.decompress(data)[:512].strip(b"\0")


# Building from source ------------------------------------------------------


def _source(tmp_path: Path, *, lock: str = "pnpm-lock.yaml") -> Path:
    root = tmp_path / "source"
    (root / "src/appmeta").mkdir(parents=True)
    (root / "src/appmeta/manifest.json").write_bytes(MANIFEST)
    (root / lock).write_text("")
    return root


class _Builds:
    """
    A build that writes what the real one would, and remembers what it ran.
    """

    def __init__(self, *, produce: bool = True, code: int = 0) -> None:
        self.commands: list[list[str]] = []
        self.produce = produce
        self.code = code

    def __call__(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        if argv[1:] == ["--version"]:
            return 0, "v25.2.1\n"
        self.commands.append([Path(argv[0]).stem, *argv[1:]])
        if argv[1:] == ["run", "build"] and self.produce:
            out = cwd / "dist/demo.app"
            (out / "appmeta").mkdir(parents=True)
            (out / "appmeta/manifest.json").write_bytes(MANIFEST)
            (out / "main.js").write_bytes(b"built")
            # What a dist folder really holds: everything ever built here.
            stale = cwd / "dist/old.app/appmeta"
            stale.mkdir(parents=True)
            (stale / "manifest.json").write_bytes(
                MANIFEST.replace(b"demo.app", b"old.app")
            )
        return self.code, "line one\nline two" if self.code else ""


def test_building_installs_then_builds_then_packs_the_right_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package.shutil, "which", lambda name: f"/bin/{name}")
    run = _Builds()
    said: list[str] = []

    result = package.build_from_source(_source(tmp_path), run=run, say=said.append)

    assert run.commands == [
        ["pnpm", "install", "--frozen-lockfile"],
        ["pnpm", "run", "build"],
    ]
    assert result.manifest.id == "demo.app"
    # dist held a stale application as well, and only ours was packed.
    assert _names(result.data) == [
        "demo.app/appmeta/manifest.json",
        "demo.app/main.js",
    ]
    assert len(said) == 3


def test_a_tree_with_an_npm_lockfile_is_built_with_npm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package.shutil, "which", lambda name: f"/bin/{name}")
    run = _Builds()

    package.build_from_source(_source(tmp_path, lock="package-lock.json"), run=run)

    assert run.commands[0] == ["npm", "ci"]


def test_without_node_the_answer_points_at_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package.shutil, "which", lambda name: None)

    with pytest.raises(ManagerError, match="released version, which needs nothing"):
        package.build_from_source(_source(tmp_path), run=_Builds())


def test_a_failed_build_shows_the_end_of_what_it_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package.shutil, "which", lambda name: f"/bin/{name}")

    with pytest.raises(
        ManagerError, match=r"(?s)installing dependencies failed.*line two"
    ):
        package.build_from_source(_source(tmp_path), run=_Builds(code=1))


def test_a_build_that_writes_nothing_where_expected_says_where_to_look(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package.shutil, "which", lambda name: f"/bin/{name}")

    with pytest.raises(ManagerError, match=r"dist/demo.app is not there"):
        package.build_from_source(_source(tmp_path), run=_Builds(produce=False))


def test_a_source_tarball_is_unpacked_into_its_one_folder(tmp_path: Path) -> None:
    data = _tar({"owner-repo-abc/src/appmeta/manifest.json": MANIFEST})

    root = package.safe_extract(data, tmp_path / "work")

    assert root.name == "owner-repo-abc"
    assert (root / "src/appmeta/manifest.json").read_bytes() == MANIFEST


def test_a_source_tarball_cannot_write_outside_its_folder(tmp_path: Path) -> None:
    with pytest.raises(ManagerError, match="unsafe path"):
        package.safe_extract(_tar({"../outside.txt": b"x"}), tmp_path / "work")

    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.parametrize(
    "name, pattern, expected",
    [
        ("app-1.0.tgz", "*.tgz", True),
        ("APP-1.0.TGZ", "*.tgz", True),
        ("app.tar.gz", "*.tgz", False),
        ("app.tar.gz", "*.tgz, *.tar.gz", True),
        ("notes.txt", "*.tgz,*.tar.gz", False),
    ],
)
def test_a_release_file_is_the_package_by_the_sources_pattern(
    name: str, pattern: str, expected: bool
) -> None:
    assert package.matches(name, pattern) is expected
