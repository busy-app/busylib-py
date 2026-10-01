"""
The manager's own memory: which sources and external apps it was told about.

One small JSON file in the place each operating system keeps per-user
settings, written atomically so a crash cannot leave half a file.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict
from pathlib import Path

from .model import Config, ExternalApp, ManagerError, Source

FORMAT_VERSION = 1
APP_DIR = "busy-apps"


def default_config_dir() -> Path:
    """
    Where this operating system keeps a program's per-user files.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return (
            Path(base) / APP_DIR if base else Path.home() / "AppData/Roaming" / APP_DIR
        )
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support" / APP_DIR
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / APP_DIR


def slugify(name: str) -> str:
    """
    A short, stable id for an external app, from the name it was given.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "app"


class Store:
    """
    Sources and external apps, kept in a file.

    Every change is written straight away: the manager is a thing people
    quit with `q` or Ctrl+C, and nobody should lose a source they just added
    because they did not leave the right way.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.dir = path.parent if path else default_config_dir()
        self.path = path or self.dir / "apps.json"
        self.config = Config()
        # Said once, at load, if the file was unreadable - it is moved aside
        # rather than overwritten, because it may be the only copy of
        # something a person typed.
        self.warning = ""

    def load(self) -> Config:
        if not self.path.exists():
            return self.config
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.config = Config(
                sources=[Source(**item) for item in raw.get("sources", [])],
                externals=[ExternalApp(**item) for item in raw.get("externals", [])],
            )
        except (OSError, ValueError, TypeError) as err:
            aside = self.path.with_suffix(".json.bad")
            try:
                self.path.replace(aside)
            except OSError:
                aside = self.path
            self.config = Config()
            self.warning = (
                f"{self.path.name} could not be read ({err}); kept as {aside.name}"
            )
        return self.config

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        document = {
            "version": FORMAT_VERSION,
            "sources": [asdict(source) for source in self.config.sources],
            "externals": [asdict(app) for app in self.config.externals],
        }
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    # Sources -----------------------------------------------------------

    def add_source(self, source: Source) -> None:
        if any(
            item.repo.lower() == source.repo.lower() and item.subdir == source.subdir
            for item in self.config.sources
        ):
            raise ManagerError(f"{source.repo} is already a source")
        self.config.sources.append(source)
        self.save()

    def remove_source(self, repo: str, subdir: str = "") -> None:
        self.config.sources = [
            item
            for item in self.config.sources
            if not (item.repo == repo and item.subdir == subdir)
        ]
        self.save()

    # External apps -----------------------------------------------------

    def save_external(self, app: ExternalApp) -> None:
        """
        Add an external app, or replace the one with the same slug.
        """
        for index, existing in enumerate(self.config.externals):
            if existing.slug == app.slug:
                self.config.externals[index] = app
                break
        else:
            self.config.externals.append(app)
        self.save()

    def remove_external(self, slug: str) -> None:
        self.config.externals = [a for a in self.config.externals if a.slug != slug]
        self.save()

    def unused_slug(self, name: str) -> str:
        taken = {app.slug for app in self.config.externals}
        slug = base = slugify(name)
        number = 2
        while slug in taken:
            slug = f"{base}-{number}"
            number += 1
        return slug
