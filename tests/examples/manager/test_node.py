from __future__ import annotations

import json
from pathlib import Path

import pytest

from examples.manager import node, package
from examples.manager.model import ManagerError


@pytest.mark.parametrize(
    "text, expected",
    [
        ("v25.2.1", (25, 2, 1)),
        ("25.2.1\n", (25, 2, 1)),
        ("v24", (24, 0, 0)),
        ("v24.x", (24, 0, 0)),
        ("nonsense", None),
        ("", None),
    ],
)
def test_what_node_prints_is_read_as_a_version(
    text: str, expected: tuple[int, int, int] | None
) -> None:
    assert node.parse_version(text) == expected


@pytest.mark.parametrize(
    "version, wanted, expected",
    [
        # What the BUSY apps actually write.
        ((24, 0, 0), ">=24 <26", True),
        ((25, 9, 9), ">=24 <26", True),
        ((26, 0, 0), ">=24 <26", False),
        ((22, 11, 0), ">=24 <26", False),
        # The other shapes people use in `engines`.
        ((24, 3, 0), "^24", True),
        ((25, 0, 0), "^24", False),
        ((24, 3, 0), "~24.3", True),
        ((24, 4, 0), "~24.3", False),
        ((24, 9, 9), "24.x", True),
        ((25, 0, 0), "24.x", False),
        ((24, 1, 0), "24", True),
        ((30, 0, 0), ">=24", True),
        ((24, 0, 0), ">24", False),
        ((25, 0, 0), ">24", True),
        ((25, 5, 0), "<=25", True),
        ((26, 0, 0), "<=25", False),
        ((20, 0, 0), "^20 || ^22 || ^24", True),
        ((21, 0, 0), "^20 || ^22 || ^24", False),
        ((99, 0, 0), "*", True),
        ((99, 0, 0), "", True),
        # Not understood: not an answer either way.
        ((24, 0, 0), "lts/*", None),
        ((24, 0, 0), "banana", None),
    ],
)
def test_the_ranges_people_write_in_engines(
    version: tuple[int, int, int], wanted: str, expected: bool | None
) -> None:
    assert node.satisfies(version, wanted) is expected


def _app(tmp_path: Path, engines: str | None) -> Path:
    (tmp_path / "package.json").write_text(
        json.dumps({"engines": {"node": engines}} if engines else {})
    )
    return tmp_path


def test_a_node_the_tooling_supports_is_let_through(tmp_path: Path) -> None:
    node.check(_app(tmp_path, ">=24 <26"), "v25.2.1")


def test_a_node_26_or_newer_is_refused_with_the_reason(tmp_path: Path) -> None:
    with pytest.raises(ManagerError) as raised:
        node.check(_app(tmp_path, ">=24 <26"), "v26.0.0")

    message = str(raised.value)
    assert "Node.js 26.0.0 is too new" in message
    assert "before 26" in message
    assert "this app asks for >=24 <26" in message
    assert "released version" in message, "and the way out that needs no Node"


def test_the_limit_holds_even_when_the_app_asks_for_nothing(tmp_path: Path) -> None:
    """
    The cap is the tooling's, not the app's: an app that never wrote it down
    is no more able to build on a newer Node.
    """
    with pytest.raises(ManagerError, match="too new"):
        node.check(_app(tmp_path, None), "v27.1.0")


def test_the_limit_holds_when_the_app_allows_anything(tmp_path: Path) -> None:
    with pytest.raises(ManagerError, match="too new"):
        node.check(_app(tmp_path, ">=18"), "v26.0.0")


def test_an_older_node_than_the_app_wants_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ManagerError, match=r"package.json asks for >=24 <26"):
        node.check(_app(tmp_path, ">=24 <26"), "v22.4.0")


def test_a_range_that_cannot_be_read_never_blocks(tmp_path: Path) -> None:
    node.check(_app(tmp_path, "lts/*"), "v24.0.0")


def test_a_version_that_cannot_be_read_never_blocks(tmp_path: Path) -> None:
    node.check(_app(tmp_path, ">=24 <26"), "something odd")


def test_a_tree_without_a_package_json_is_only_held_to_the_cap(tmp_path: Path) -> None:
    node.check(tmp_path, "v24.0.0")
    with pytest.raises(ManagerError, match="too new"):
        node.check(tmp_path, "v26.0.0")


# In the build -----------------------------------------------------------------

MANIFEST = b'{"id": "demo.app", "name": "Demo", "version": "1.2.0"}'


def _source(tmp_path: Path, engines: str = ">=24 <26") -> Path:
    root = tmp_path / "source"
    (root / "src/appmeta").mkdir(parents=True)
    (root / "src/appmeta/manifest.json").write_bytes(MANIFEST)
    (root / "pnpm-lock.yaml").write_text("")
    (root / "package.json").write_text(json.dumps({"engines": {"node": engines}}))
    return root


class _Runs:
    def __init__(self, node_version: str) -> None:
        self.node_version = node_version
        self.commands: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        self.commands.append([Path(argv[0]).stem, *argv[1:]])
        if argv[1:] == ["--version"]:
            return 0, self.node_version + "\n"
        if argv[1:] == ["run", "build"]:
            out = cwd / "dist/demo.app/appmeta"
            out.mkdir(parents=True)
            (out / "manifest.json").write_bytes(MANIFEST)
        return 0, ""


def test_a_build_on_a_node_that_is_too_new_stops_before_installing_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Installing downloads packages for a Node that cannot use them, and the
    failure that follows blames the app.
    """
    monkeypatch.setattr(package.shutil, "which", lambda name: f"/bin/{name}")
    run = _Runs("v26.1.0")

    with pytest.raises(ManagerError, match="too new"):
        package.build_from_source(_source(tmp_path), run=run)

    assert run.commands == [["node", "--version"]]


def test_a_build_on_a_supported_node_goes_ahead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package.shutil, "which", lambda name: f"/bin/{name}")
    run = _Runs("v25.2.1")

    result = package.build_from_source(_source(tmp_path), run=run)

    assert result.manifest.id == "demo.app"
    assert [c[0] for c in run.commands] == ["node", "pnpm", "pnpm"]


def test_a_missing_node_says_what_to_install_and_that_releases_need_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        package.shutil, "which", lambda name: None if name == "node" else f"/bin/{name}"
    )

    with pytest.raises(
        ManagerError, match=r"Node.js \(before version 26\).*released version"
    ):
        package.build_from_source(_source(tmp_path), run=_Runs("v25.0.0"))
