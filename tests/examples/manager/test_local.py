"""
A folder on this computer as a place an app comes from.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from examples.manager import localrepo
from examples.manager.model import ManagerError

needs_git = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)


def _git(folder: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(folder), "-c", "user.name=T", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def _names(data: bytes) -> set[str]:
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return {m.name for m in tar if m.isfile()}


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("busy-app/demo", False),
        ("https://github.com/busy-app/demo", False),
        ("/home/me/app", True),
        ("~/projects/app", True),
        ("./app", True),
        ("../app", True),
        ("C:\\Users\\me\\app", True),
        ("c:/Users/me/app", True),
    ],
)
def test_a_path_is_told_from_a_repository_by_how_it_is_written(
    typed: str, expected: bool
) -> None:
    assert localrepo.looks_like_path(typed) is expected


def test_a_folder_in_the_current_one_counts_even_without_a_dot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "my app").mkdir()
    monkeypatch.chdir(tmp_path)

    assert localrepo.looks_like_path("my app") is True
    assert localrepo.looks_like_path("nothing here") is False


def test_a_path_resolves_to_a_folder_or_says_it_is_not_one(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("x")

    assert localrepo.resolve(str(tmp_path)) == tmp_path.resolve()
    with pytest.raises(ManagerError, match="is not a folder"):
        localrepo.resolve(str(tmp_path / "file"))
    with pytest.raises(ManagerError, match="is not a folder"):
        localrepo.resolve(str(tmp_path / "missing"))


def test_a_copy_of_the_working_copy_leaves_out_what_a_build_makes(
    tmp_path: Path,
) -> None:
    """
    The build runs on the copy, so nothing is left in the project, and an old
    build's output cannot be mistaken for the new one.
    """
    for name in (
        "src/appmeta/manifest.json",
        "package.json",
        "node_modules/x/index.js",
        "dist/demo.app/main.js",
        ".git/config",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x")

    assert _names(localrepo.snapshot(tmp_path)) == {
        "src/appmeta/manifest.json",
        "package.json",
    }


@needs_git
def test_the_commits_of_a_repository_are_listed_newest_first(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a").write_text("1")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "first one")
    (tmp_path / "a").write_text("2")
    _git(tmp_path, "commit", "-qam", "second one")

    found = localrepo.commits(tmp_path)

    assert [v.label.split(" ", 1)[1] for v in found] == ["second one", "first one"]
    assert all(v.kind == "commit" and len(v.ref) == 40 for v in found)
    assert found[0].published and found[0].note == "T"


@needs_git
def test_a_commit_is_taken_out_as_it_was_not_as_it_is(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a").write_text("old")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "old")
    old = localrepo.commits(tmp_path)[0].ref
    (tmp_path / "a").write_text("new")
    (tmp_path / "b").write_text("later")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "new")

    with tarfile.open(fileobj=io.BytesIO(localrepo.archive(tmp_path, old))) as tar:
        member = tar.extractfile("a")
        assert member is not None and member.read() == b"old"
        assert "b" not in tar.getnames()


@needs_git
def test_a_commit_that_is_an_option_is_refused_not_passed_to_git(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    with pytest.raises(ManagerError, match="not a commit"):
        localrepo.archive(tmp_path, "--output=/tmp/x")


@needs_git
def test_a_commit_that_is_not_there_is_git_s_complaint(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    with pytest.raises(ManagerError, match="git archive failed"):
        localrepo.archive(tmp_path, "deadbeef")


@needs_git
def test_the_working_copy_says_where_it_sits_and_whether_it_has_changes(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a").write_text("1")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "one")

    clean = localrepo.head(tmp_path)
    (tmp_path / "a").write_text("2")

    assert len(clean) >= 7 and "changes" not in clean
    assert localrepo.head(tmp_path) == f"{clean} + changes"


def test_a_folder_that_is_not_a_repository_has_no_commits(tmp_path: Path) -> None:
    with pytest.raises(ManagerError, match="not a git repository"):
        localrepo.commits(tmp_path)
    assert localrepo.head(tmp_path) == ""


def test_without_git_the_commits_say_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(localrepo.shutil, "which", lambda name: None)

    with pytest.raises(ManagerError, match="not a git repository"):
        localrepo.commits(tmp_path)
    with pytest.raises(ManagerError, match="git is not installed"):
        localrepo.archive(tmp_path, "main")
