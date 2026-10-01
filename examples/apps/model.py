"""
What the app manager talks about: apps, where they come from, and which
version of them to take.

Nothing here touches the network, the disk or the bar. The other modules
produce and consume these, which is what lets each of them be tested
without the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

# The bar's own rule for an application id, from its API: it is also a
# folder name on the bar, so it stays short and plain.
APP_ID = re.compile(r"^[a-zA-Z0-9_\-][a-zA-Z0-9_\-.]{0,31}$")
# GitHub's own rules, not just "letters and slashes": an owner starts with a
# letter or digit, and a repository can be called nearly anything except `.`
# or `..` - which, left in, turn "owner/name" into a walk up the API's paths.
REPO = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,38}/(?!\.{1,2}$)[A-Za-z0-9_.\-]{1,100}$"
)

# The bar refuses a package larger than this with a 413.
MAX_PACKAGE_BYTES = 100 * 1024 * 1024


class ManagerError(Exception):
    """
    Something went wrong that the person should be told about in words.

    Everything the manager raises on purpose is one of these, so the
    interface can show the message and carry on; anything else is a bug and
    is allowed to be loud.
    """


@dataclass(frozen=True)
class AppManifest:
    """
    The part of an application's manifest the manager shows and checks.

    The file has more in it (heap size, a format version, a debug flag); the
    bar reads those, and the manager has no opinion about them.
    """

    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""

    @classmethod
    def from_json(cls, raw: object) -> AppManifest:
        if not isinstance(raw, dict):
            raise ManagerError("the manifest is not a JSON object")
        missing = [key for key in ("id", "name", "version") if not raw.get(key)]
        if missing:
            raise ManagerError(f"the manifest has no {', '.join(missing)}")
        app_id = str(raw["id"])
        if not APP_ID.match(app_id):
            raise ManagerError(
                f"{app_id!r} is not an application id the bar accepts: letters, "
                "digits, '_', '-' and '.', at most 32 characters"
            )
        return cls(
            id=app_id,
            name=str(raw["name"]),
            version=str(raw["version"]),
            description=str(raw.get("description") or ""),
            author=str(raw.get("author") or ""),
        )


@dataclass(frozen=True)
class Package:
    """
    A tgz the bar will accept, and what it says it is.
    """

    manifest: AppManifest
    data: bytes


@dataclass
class Source:
    """
    A place applications come from: one GitHub repository.

    `mode` is how a version of it becomes a package. `release` downloads the
    package a maintainer attached to a GitHub release, which needs nothing
    installed. `build` downloads the source at a tag or branch and builds it,
    which needs Node and pnpm and is for trying something that has not been
    released.

    `manifest` is where in the repository the application's manifest lives,
    when it is not one of the places looked in by default. `asset` picks the
    package out of a release that has several files. `subdir` is for a
    repository that holds more than one application.
    """

    repo: str
    mode: Literal["release", "build"] = "release"
    manifest: str = ""
    asset: str = "*.tgz"
    subdir: str = ""
    title: str = ""

    @property
    def label(self) -> str:
        return self.title or self.repo


@dataclass
class ExternalApp:
    """
    A program that is not on the bar but belongs with it: a script that
    draws on the display, a bridge, a dashboard.

    It is a card (a name and a line about it) plus what is needed to run
    it: a folder and a command. Nothing about it is checked until it is run.
    """

    slug: str
    name: str
    path: str
    command: str
    description: str = ""


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int = 0


@dataclass(frozen=True)
class Version:
    """
    One thing a source can be installed at.

    A release carries the package itself in `asset`; a tag or a branch has
    none, and is built from source.
    """

    ref: str
    label: str
    kind: Literal["release", "tag", "branch"]
    asset: Asset | None = None
    published: str = ""
    prerelease: bool = False


@dataclass
class Config:
    sources: list[Source] = field(default_factory=list)
    externals: list[ExternalApp] = field(default_factory=list)
