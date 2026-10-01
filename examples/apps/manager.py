"""
What the manager does, without any of how it looks.

The interface asks this for the list of applications, tells it to install,
launch, quit or remove one, and shows what comes back. Keeping the sequence
here - download or build, check, hand to the bar, ask, install - is what lets
it be tested without a terminal, and what keeps the interface from knowing
how a package is made.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from busylib import types

from . import package
from .bar import Bar, replacing
from .github import GitHub
from .launcher import Launcher
from .model import ExternalApp, ManagerError, Package, Source, Version
from .store import Store

Say = Callable[[str], None]


@dataclass(frozen=True)
class Entry:
    """
    One line of the list: an application on the bar, or an external one.
    """

    key: str
    kind: Literal["bar", "external"]
    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    ident: str = ""
    status: str = ""
    info: types.AppInfo | None = None
    external: ExternalApp | None = None

    @property
    def where(self) -> str:
        return "bar" if self.kind == "bar" else "computer"


@dataclass
class Prepared:
    """
    A package the bar is holding, waiting to be told to install it.
    """

    package: Package
    staged: types.AppStageResult

    @property
    def summary(self) -> str:
        return replacing(self.staged)


class Manager:
    def __init__(
        self,
        store: Store,
        github: GitHub,
        launcher: Launcher,
        bar: Bar | None = None,
        *,
        run: package.Runner = package.run_command,
    ) -> None:
        self.store = store
        self.github = github
        self.launcher = launcher
        self.bar = bar
        self.run = run

    # The list ----------------------------------------------------------

    async def entries(self) -> tuple[list[Entry], str]:
        """
        Everything there is to start, and a sentence about what went wrong
        reaching the bar, if anything did.

        A bar that does not answer must not hide the external apps, which
        have nothing to do with it - so the problem is returned beside the
        list rather than raised in place of it.
        """
        problem = ""
        listed: list[Entry] = []
        if self.bar is None:
            problem = "not connected to a bar (running with --offline)"
        else:
            try:
                for info in await self.bar.installed():
                    listed.append(
                        Entry(
                            key=f"bar:{info.id}",
                            kind="bar",
                            name=info.name,
                            version=info.version,
                            description=info.description,
                            author=info.author,
                            ident=info.id,
                            status="debug" if info.is_debug else "installed",
                            info=info,
                        )
                    )
            except ManagerError as err:
                problem = str(err)
        listed.sort(key=lambda entry: entry.name.lower())

        external = [
            Entry(
                key=f"external:{app.slug}",
                kind="external",
                name=app.name,
                description=app.description,
                ident=app.slug,
                status="running" if self.launcher.is_running(app) else "ready",
                external=app,
            )
            for app in sorted(self.store.config.externals, key=lambda a: a.name.lower())
        ]
        return listed + external, problem

    # Sources -----------------------------------------------------------

    async def add_source(self, source: Source) -> Source:
        """
        Add a source after checking there is something to install from it.

        Asking GitHub now rather than at install time is what turns a typo
        in the repository name into a message in the form that was just
        filled in, instead of a puzzle later.
        """
        versions = await asyncio.to_thread(self.github.versions, source)
        manifest = await asyncio.to_thread(
            self.github.manifest, source, versions[0].ref
        )
        if manifest is not None and not source.title:
            source.title = manifest.name
        self.store.add_source(source)
        return source

    async def versions(self, source: Source) -> list[Version]:
        return await asyncio.to_thread(self.github.versions, source)

    # Installing --------------------------------------------------------

    async def prepare(self, source: Source, version: Version, say: Say) -> Prepared:
        """
        Get a package for this version, and give it to the bar to hold.

        The bar unpacks it and says what it would replace; nothing on the bar
        changes until `commit`. That is what allows asking first.
        """
        if self.bar is None:
            raise ManagerError("there is no bar to install on (running with --offline)")

        if version.kind == "release":
            say(f"downloading {version.asset.name if version.asset else version.label}")
            data = await asyncio.to_thread(self.github.release_package, version)
            say("checking the package")
            built = await asyncio.to_thread(package.normalize_package, data)
        else:
            say(f"downloading the source at {version.ref}")
            archive = await asyncio.to_thread(
                self.github.source_archive, source, version.ref
            )
            built = await asyncio.to_thread(self._build, archive, source, say)

        say(
            f"{built.manifest.name} {built.manifest.version} ({built.manifest.id}), "
            f"{len(built.data) // 1024 or 1} KiB"
        )
        say("handing it to the bar")
        staged = await self.bar.stage(built.data)
        if staged.staged.id != built.manifest.id:
            raise ManagerError(
                f"the bar read the package as {staged.staged.id!r}, not "
                f"{built.manifest.id!r}; refusing to install it"
            )
        return Prepared(built, staged)

    def _build(self, archive: bytes, source: Source, say: Say) -> Package:
        with tempfile.TemporaryDirectory(prefix="busy-apps-") as temporary:
            root = package.safe_extract(archive, Path(temporary))
            folder = root / source.subdir if source.subdir else root
            if not folder.is_dir():
                raise ManagerError(
                    f"{source.subdir!r} is not a folder in {source.repo}"
                )
            return package.build_from_source(
                folder, manifest_hint=source.manifest, run=self.run, say=say
            )

    async def commit(self, prepared: Prepared) -> None:
        if self.bar is None:
            raise ManagerError("there is no bar to install on")
        await self.bar.install(prepared.staged)

    # Using what is there -----------------------------------------------

    async def activate(self, entry: Entry) -> str:
        """
        Start an entry: launch it on the bar, or run it on this computer.
        Returns a sentence about what happened.
        """
        if entry.kind == "bar":
            if self.bar is None:
                raise ManagerError(
                    "there is no bar to launch on (running with --offline)"
                )
            await self.bar.launch(entry.ident)
            return f"Launched {entry.name} on the bar"
        assert entry.external is not None
        pid = await asyncio.to_thread(self.launcher.start, entry.external)
        return f"Started {entry.name} (process {pid})"

    async def stop(self, entry: Entry | None) -> str:
        """
        Stop what is running: the selected external app, or whatever the
        bar is running (the bar has one app at a time, so there is no
        choosing).
        """
        if entry is not None and entry.kind == "external" and entry.external:
            if self.launcher.stop(entry.external):
                return f"Stopped {entry.name}"
            raise ManagerError(f"{entry.name} is not running")
        if self.bar is None:
            raise ManagerError(
                "there is no bar to quit an app on (running with --offline)"
            )
        await self.bar.quit()
        return "Quit the app on the bar"

    async def remove(self, entry: Entry) -> str:
        if entry.kind == "bar":
            if self.bar is None:
                raise ManagerError(
                    "there is no bar to remove from (running with --offline)"
                )
            await self.bar.delete(entry.ident)
            return f"Removed {entry.name} from the bar (its settings are kept)"
        if entry.external is not None:
            self.launcher.stop(entry.external)
        self.store.remove_external(entry.ident)
        return f"Forgot {entry.name} (nothing on disk was deleted)"

    # External apps -----------------------------------------------------

    def add_external(
        self, name: str, path: str, command: str, description: str
    ) -> ExternalApp:
        app = self._external(
            self.store.unused_slug(name), name, path, command, description
        )
        self.store.save_external(app)
        return app

    def edit_external(
        self, app: ExternalApp, name: str, path: str, command: str, description: str
    ) -> ExternalApp:
        updated = self._external(app.slug, name, path, command, description)
        self.store.save_external(updated)
        return updated

    @staticmethod
    def _external(
        slug: str, name: str, path: str, command: str, description: str
    ) -> ExternalApp:
        """
        An external app, if what was typed describes one that could run.

        The folder is checked now because it is the one mistake that is
        certain; the command is not, since only running it shows whether it
        works.
        """
        if not name.strip():
            raise ManagerError("give it a name")
        folder = Path(path).expanduser()
        if not folder.is_dir():
            raise ManagerError(f"{folder} is not a folder")
        if not command.strip():
            raise ManagerError("say what command starts it")
        return ExternalApp(
            slug=slug,
            name=name.strip(),
            path=str(folder),
            command=command.strip(),
            description=description.strip(),
        )
