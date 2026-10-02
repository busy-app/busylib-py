"""
The manager's own memory: the sources it was told about, the programs on this
computer, and what each source last offered.

One SQLite file in the place each operating system keeps per-user settings.
Every change is committed at once - the manager is a thing people quit with
`q` or Ctrl+C, and nobody should lose a source they just added because they
did not leave the right way. A file that cannot be read is moved aside rather
than overwritten, because it may be the only copy of something a person typed.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .model import Config, ExternalApp, ManagerError, Offer, Source

APP_DIR = "busy-apps"
DB_NAME = "apps.db"
# The file this manager kept before it had a database; read once, then left.
LEGACY_NAME = "apps.json"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    repo TEXT NOT NULL COLLATE NOCASE,
    subdir TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'release',
    manifest TEXT NOT NULL DEFAULT '',
    asset TEXT NOT NULL DEFAULT '*.tgz',
    title TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'app',
    branch TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL,
    PRIMARY KEY (repo, subdir)
);
CREATE TABLE IF NOT EXISTS externals (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    command TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    env TEXT NOT NULL DEFAULT '{}',
    python TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS offers (
    repo TEXT NOT NULL COLLATE NOCASE,
    subdir TEXT NOT NULL DEFAULT '',
    slug TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    app_id TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (repo, subdir, slug)
);
"""


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
    Sources, external apps and offers, kept in a database.

    `config` mirrors the first two in memory for the interface to read; every
    change goes to the file first.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.dir = path.parent if path else default_config_dir()
        self.path = path or self.dir / DB_NAME
        self.config = Config()
        # Said once, at load, if the file was unreadable.
        self.warning = ""

    # Opening -----------------------------------------------------------

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.dir.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.executescript(SCHEMA)
                yield db
        finally:
            db.close()

    def load(self) -> Config:
        """
        Read what is kept. A first run has nothing and writes nothing.
        """
        legacy = self.path.with_name(LEGACY_NAME)
        if not self.path.exists() and not legacy.exists():
            return self.config
        try:
            with self._db() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise sqlite3.DatabaseError(
                        f"written by a newer manager (format {version})"
                    )
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                if legacy.exists() and not self._any(db):
                    self._import_legacy(db, legacy)
                self.config = self._read(db)
        except (sqlite3.DatabaseError, OSError, ValueError, TypeError) as err:
            self._set_aside(err)
        return self.config

    @staticmethod
    def _any(db: sqlite3.Connection) -> bool:
        return bool(
            db.execute(
                "SELECT (SELECT COUNT(*) FROM sources) + "
                "(SELECT COUNT(*) FROM externals)"
            ).fetchone()[0]
        )

    def _set_aside(self, err: Exception) -> None:
        aside = self.path.with_name(self.path.name + ".bad")
        try:
            self.path.replace(aside)
        except OSError:
            aside = self.path
        self.config = Config()
        self.warning = (
            f"{self.path.name} could not be read ({err}); kept as {aside.name}"
        )

    @staticmethod
    def _read(db: sqlite3.Connection) -> Config:
        sources = [
            Source(
                repo=row["repo"],
                mode=row["mode"],
                manifest=row["manifest"],
                asset=row["asset"],
                subdir=row["subdir"],
                title=row["title"],
                kind=row["kind"],
                branch=row["branch"],
            )
            for row in db.execute("SELECT * FROM sources ORDER BY position")
        ]
        externals = [
            ExternalApp(
                slug=row["slug"],
                name=row["name"],
                path=row["path"],
                command=row["command"],
                description=row["description"],
                env=json.loads(row["env"]),
                python=row["python"],
            )
            for row in db.execute("SELECT * FROM externals ORDER BY position")
        ]
        return Config(sources=sources, externals=externals)

    def _import_legacy(self, db: sqlite3.Connection, legacy: Path) -> None:
        """
        Take in the file this manager used before it had a database. It is
        renamed afterwards, not deleted: it is still a copy of what was typed.
        """
        raw = json.loads(legacy.read_text(encoding="utf-8"))
        for item in raw.get("sources", []):
            self._insert_source(db, Source(**item))
        for item in raw.get("externals", []):
            self._upsert_external(db, ExternalApp(**item))
        legacy.replace(legacy.with_name(legacy.name + ".imported"))

    # Sources -----------------------------------------------------------

    @staticmethod
    def _insert_source(db: sqlite3.Connection, source: Source) -> None:
        db.execute(
            "INSERT INTO sources (repo, subdir, mode, manifest, asset, title, kind,"
            " branch, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?,"
            " (SELECT COALESCE(MAX(position), 0) + 1 FROM sources))",
            (
                source.repo,
                source.subdir,
                source.mode,
                source.manifest,
                source.asset,
                source.title,
                source.kind,
                source.branch,
            ),
        )

    def add_source(self, source: Source) -> None:
        try:
            with self._db() as db:
                self._insert_source(db, source)
        except sqlite3.IntegrityError:
            raise ManagerError(f"{source.repo} is already a source") from None
        self.config.sources.append(source)

    def remove_source(self, repo: str, subdir: str = "") -> None:
        with self._db() as db:
            db.execute(
                "DELETE FROM sources WHERE repo = ? AND subdir = ?", (repo, subdir)
            )
            db.execute(
                "DELETE FROM offers WHERE repo = ? AND subdir = ?", (repo, subdir)
            )
        self.config.sources = [
            item
            for item in self.config.sources
            if not (item.repo.lower() == repo.lower() and item.subdir == subdir)
        ]

    # Offers ------------------------------------------------------------

    def offers(self) -> list[Offer]:
        """
        What every source last offered, in the order the sources were added.
        """
        try:
            with self._db() as db:
                rows = db.execute(
                    "SELECT offers.* FROM offers JOIN sources USING (repo, subdir) "
                    "ORDER BY sources.position, offers.name COLLATE NOCASE"
                ).fetchall()
        except sqlite3.DatabaseError:
            return []
        return [Offer(**dict(row)) for row in rows]

    def set_offers(self, repo: str, subdir: str, offers: list[Offer]) -> None:
        """
        Replace what a source offers with what it was just seen to offer.
        """
        with self._db() as db:
            db.execute(
                "DELETE FROM offers WHERE repo = ? AND subdir = ?", (repo, subdir)
            )
            db.executemany(
                "INSERT INTO offers (repo, subdir, slug, name, version, description,"
                " author, app_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        repo,
                        subdir,
                        o.slug,
                        o.name,
                        o.version,
                        o.description,
                        o.author,
                        o.app_id,
                    )
                    for o in offers
                ],
            )

    # External apps -----------------------------------------------------

    @staticmethod
    def _upsert_external(db: sqlite3.Connection, app: ExternalApp) -> None:
        db.execute(
            "INSERT INTO externals (slug, name, path, command, description, env,"
            " python, position) VALUES (?, ?, ?, ?, ?, ?, ?,"
            " (SELECT COALESCE(MAX(position), 0) + 1 FROM externals))"
            " ON CONFLICT (slug) DO UPDATE SET name = excluded.name,"
            " path = excluded.path, command = excluded.command,"
            " description = excluded.description, env = excluded.env,"
            " python = excluded.python",
            (
                app.slug,
                app.name,
                app.path,
                app.command,
                app.description,
                json.dumps(app.env),
                app.python,
            ),
        )

    def save_external(self, app: ExternalApp) -> None:
        """
        Add an external app, or replace the one with the same slug.
        """
        with self._db() as db:
            self._upsert_external(db, app)
        for index, existing in enumerate(self.config.externals):
            if existing.slug == app.slug:
                self.config.externals[index] = app
                break
        else:
            self.config.externals.append(app)

    def remove_external(self, slug: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM externals WHERE slug = ?", (slug,))
        self.config.externals = [a for a in self.config.externals if a.slug != slug]

    def unused_slug(self, name: str) -> str:
        taken = {app.slug for app in self.config.externals}
        slug = base = slugify(name)
        number = 2
        while slug in taken:
            slug = f"{base}-{number}"
            number += 1
        return slug
