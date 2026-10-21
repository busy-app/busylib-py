"""
A folder on this computer as a place an app comes from.

It may be a git repository, in which case any commit of it can be built, or
just a folder, in which case the working copy is what there is. Either way
the build happens on a copy: a project is not somewhere to leave
`node_modules` and `dist` that its owner did not ask for.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

from .model import REPO, ManagerError, Version

# Left out of a copy of the working copy: git's own files, installed
# dependencies and an earlier build's output, which the new build replaces.
_SKIPPED = {".git", "node_modules", "dist", "__MACOSX"}
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_SEPARATOR = "\x1f"


def looks_like_path(text: str) -> bool:
    """
    Whether what was typed names a folder rather than a GitHub repository.

    `owner/name` is a repository unless it is written as a path: from the
    root, the home directory, here, or a drive.
    """
    text = text.strip()
    if text.startswith(("/", "~", ".", "\\")) or _DRIVE.match(text):
        return True
    return not REPO.match(text) and Path(text).expanduser().is_dir()


def resolve(text: str) -> Path:
    folder = Path(text.strip()).expanduser()
    try:
        folder = folder.resolve()
    except OSError as err:
        raise ManagerError(f"{text!r} is not a usable path ({err})") from err
    if not folder.is_dir():
        raise ManagerError(f"{folder} is not a folder")
    return folder


def _git(folder: Path, *args: str) -> bytes:
    tool = shutil.which("git")
    if tool is None:
        raise ManagerError("git is not installed, so commits cannot be listed or built")
    try:
        done = subprocess.run(
            [tool, "-C", str(folder), *args],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        raise ManagerError(f"git did not run ({err})") from err
    if done.returncode != 0:
        said = done.stderr.decode("utf-8", errors="replace").strip()
        raise ManagerError(f"git {args[0]} failed: {said or done.returncode}")
    return done.stdout


def is_git(folder: Path) -> bool:
    try:
        return _git(folder, "rev-parse", "--is-inside-work-tree").strip() == b"true"
    except ManagerError:
        return False


def head(folder: Path) -> str:
    """
    What the working copy is, in a few words: the commit it sits on, and
    whether it has changes of its own.
    """
    if not is_git(folder):
        return ""
    try:
        sha = _git(folder, "rev-parse", "--short", "HEAD").decode().strip()
        dirty = bool(_git(folder, "status", "--porcelain").strip())
    except ManagerError:
        return ""
    return f"{sha} + changes" if dirty else sha


def commits(folder: Path, limit: int = 30) -> list[Version]:
    """
    The newest commits of the repository the folder is in.
    """
    if not is_git(folder):
        raise ManagerError(f"{folder} is not a git repository")
    fields = _SEPARATOR.join(("%H", "%cI", "%an", "%s"))
    out = _git(folder, "log", f"-n{limit}", f"--format={fields}").decode(
        "utf-8", errors="replace"
    )
    found: list[Version] = []
    for line in out.splitlines():
        sha, date, author, subject = (line.split(_SEPARATOR) + ["", "", "", ""])[:4]
        if sha:
            found.append(
                Version(
                    ref=sha,
                    label=f"{sha[:7]} {subject}".strip(),
                    kind="commit",
                    published=date,
                    note=author,
                )
            )
    if not found:
        raise ManagerError(f"{folder} has no commits yet")
    return found


def archive(folder: Path, ref: str) -> bytes:
    """
    The tree at a commit, as a tar, for the folder and what is under it.
    """
    if ref.startswith("-"):
        raise ManagerError(f"{ref!r} is not a commit")
    return _git(folder, "archive", "--format=tar", ref, "--", ".")


def snapshot(folder: Path) -> bytes:
    """
    The working copy as it is now, as a tar.
    """
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for path in sorted(folder.rglob("*")):
            relative = path.relative_to(folder)
            if _SKIPPED & set(relative.parts) or not path.is_file():
                continue
            if path.is_symlink():
                continue
            tar.add(path, arcname=relative.as_posix(), recursive=False)
    return out.getvalue()
