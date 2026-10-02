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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from busylib import types

from . import catalog as catalogs
from . import package
from .bar import Bar, replacing
from .github import GitHub
from .launcher import Launcher, parse_env
from .model import (
    ExternalApp,
    ManagerError,
    Offer,
    Package,
    Source,
    Version,
    parse_repo,
)
from .programs import Installed, Plan, Programs, needs_update
from .store import Store

Say = Callable[[str], None]


@dataclass(frozen=True)
class Entry:
    """
    One line of the list: an application on the bar, or an external one.
    """

    key: str
    kind: Literal["bar", "external", "available"]
    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    ident: str = ""
    status: str = ""
    info: types.AppInfo | None = None
    external: ExternalApp | None = None
    # For a program installed from a catalog: which repository, and whether
    # the catalog now has something newer.
    origin: str = ""
    update: bool = False
    # For one a source offers and nothing has installed yet: what it offers,
    # and whether it would go on the bar or on this computer.
    offer: Offer | None = None
    target: str = ""

    @property
    def where(self) -> str:
        return self.target or ("bar" if self.kind == "bar" else "computer")

    def with_running(self, running: bool) -> Entry:
        """
        This entry, with the status its process implies: running while it
        runs, and otherwise whatever it is when idle.
        """
        if running:
            return replace(self, status="running")
        return replace(self, status="update" if self.update else "ready")


@dataclass
class Prepared:
    """
    A package the bar is holding, waiting to be told to install it.
    """

    package: Package
    staged: types.AppStageResult
    source: Source | None = None

    @property
    def summary(self) -> str:
        return replacing(self.staged)


@dataclass
class ProgramPrepared:
    """
    A program about to be installed from a catalog, and what that will do.
    """

    source: Source
    catalog: catalogs.Catalog
    app: catalogs.CatalogApp
    plan: Plan

    @property
    def summary(self) -> str:
        plan = self.plan
        verb = "Update" if plan.replaces else "Install"
        text = (
            f"{verb} {self.app.name} ({plan.files} file(s), "
            f"{max(plan.size // 1024, 1)} KiB) in {plan.folder}."
        )
        if plan.packages:
            text += f" It needs the packages {', '.join(plan.packages)}."
        return text + (
            " It runs on this computer with your permissions, so install only "
            "what you trust."
        )


class Manager:
    def __init__(
        self,
        store: Store,
        github: GitHub,
        launcher: Launcher,
        bar: Bar | None = None,
        *,
        run: package.Runner = package.run_command,
        programs: Programs | None = None,
    ) -> None:
        self.store = store
        self.github = github
        self.launcher = launcher
        self.bar = bar
        self.run = run
        self.programs = programs or Programs(store.dir / "programs", github, run=run)
        # What the catalogs said the last time they were asked, by repository.
        self.catalogs: dict[str, catalogs.Catalog] = {}

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

        external = [self._external_entry(app) for app in self.store.config.externals]
        external.sort(key=lambda entry: entry.name.lower())
        return listed + external + self._available(listed, external), problem

    def _available(self, on_bar: list[Entry], external: list[Entry]) -> list[Entry]:
        """
        What the sources offer that is not installed, as the last look at
        them saw it - so the list has them before the network has answered,
        and without it.
        """
        sources = {(s.repo.lower(), s.subdir): s for s in self.store.config.sources}
        on_the_bar = {entry.ident for entry in on_bar}
        folders = {Path(e.external.path) for e in external if e.external}
        found: list[Entry] = []
        for offer in self.store.offers():
            source = sources.get((offer.repo.lower(), offer.subdir))
            if source is None:
                continue
            if source.kind == "catalog":
                if self.programs.folder(offer.slug) in folders:
                    continue
            elif offer.app_id and offer.app_id in on_the_bar:
                continue
            found.append(
                Entry(
                    key=f"available:{offer.repo}|{offer.subdir}|{offer.slug}",
                    kind="available",
                    name=offer.name,
                    version=offer.version,
                    description=offer.description,
                    author=offer.author,
                    ident=offer.slug or offer.repo,
                    status="not installed",
                    origin=offer.repo,
                    offer=offer,
                    target="computer" if source.kind == "catalog" else "bar",
                )
            )
        return found

    def source_of(self, entry: Entry) -> Source | None:
        """
        The source an available entry is offered by.
        """
        offer = entry.offer
        if offer is None:
            return None
        return next(
            (
                s
                for s in self.store.config.sources
                if s.repo.lower() == offer.repo.lower() and s.subdir == offer.subdir
            ),
            None,
        )

    def _external_entry(self, app: ExternalApp) -> Entry:
        stamp = self.stamp_of(app)
        update = stamp is not None and self.has_update(stamp, app)
        if self.launcher.is_running(app):
            status = "running"
        else:
            status = "update" if update else "ready"
        return Entry(
            key=f"external:{app.slug}",
            kind="external",
            name=app.name,
            description=app.description,
            ident=app.slug,
            status=status,
            external=app,
            origin=stamp.repo if stamp else "",
            update=update,
        )

    def stamp_of(self, app: ExternalApp) -> Installed | None:
        """
        Where a program came from, if the manager installed it.
        """
        folder = Path(app.path)
        if folder.parent != self.programs.root:
            return None
        return self.programs.stamp(folder.name)

    def has_update(self, stamp: Installed, app: ExternalApp) -> bool:
        catalog = self.catalogs.get(stamp.repo)
        found = catalog.find(Path(app.path).name) if catalog else None
        return found is not None and needs_update(stamp, found)

    # Sources -----------------------------------------------------------

    async def add_repo(self, text: str) -> Source:
        """
        Add a source from nothing but where it is: `owner/name`, or a link.

        What kind of source it is gets worked out here, and whatever it
        offers appears in the list as not installed.
        """
        repo = parse_repo(text)
        if any(s.repo.lower() == repo.lower() for s in self.store.config.sources):
            raise ManagerError(f"{repo} is already a source")
        return await self.add_source(await self.detect(repo))

    async def detect(self, repo: str) -> Source:
        """
        What a repository is for: a catalog of programs (an `apps/` folder of
        them), an app with releases to install, or an app to build from source.
        """
        try:
            as_catalog = Source(repo=repo, kind="catalog")
            if (await self.catalog(as_catalog)).apps:
                return as_catalog
        except ManagerError:
            pass  # not a catalog; the next question says if it is not there at all
        try:
            await asyncio.to_thread(self.github.versions, Source(repo=repo))
            return Source(repo=repo)
        except ManagerError:
            pass
        built = Source(repo=repo, mode="build")
        versions = await asyncio.to_thread(self.github.versions, built)
        if await asyncio.to_thread(self.github.manifest, built, versions[0].ref):
            return built
        raise ManagerError(
            f"{repo} has nothing to install: no apps/ folder of programs, no release "
            "with a .tgz package, and no app manifest in its source"
        )

    async def add_source(self, source: Source) -> Source:
        """
        Add a source after checking there is something to install from it.

        Asking GitHub now rather than at install time is what turns a typo
        in the repository name into a message in the form that was just
        filled in, instead of a puzzle later.
        """
        offers = await self._look(source)
        if source.kind == "catalog":
            if not offers:
                problems = self.catalogs[source.repo].problems
                raise ManagerError(
                    f"{source.repo} has no programs in its apps/ folder"
                    + (f" ({len(problems)} could not be read)" if problems else "")
                )
            source.title = source.title or source.repo.split("/", 1)[1]
        elif not source.title and offers[0].app_id:
            source.title = offers[0].name
        self.store.add_source(source)
        self.store.set_offers(source.repo, source.subdir, offers)
        return source

    async def _look(self, source: Source) -> list[Offer]:
        """
        What a source has to install right now.
        """
        repo, subdir = source.repo, source.subdir
        if source.kind == "catalog":
            found = await self.catalog(source)
            return [
                Offer(
                    repo,
                    subdir,
                    app.slug,
                    app.name,
                    description=app.manifest.description,
                    author=app.manifest.author,
                )
                for app in found.apps
            ]
        versions = await asyncio.to_thread(self.github.versions, source)
        manifest = await asyncio.to_thread(
            self.github.manifest, source, versions[0].ref
        )
        if manifest is None:
            return [Offer(repo, subdir, "", source.label, versions[0].label)]
        return [
            Offer(
                repo,
                subdir,
                "",
                manifest.name,
                manifest.version,
                manifest.description,
                manifest.author,
                manifest.id,
            )
        ]

    def forget_source(self, source: Source) -> None:
        self.store.remove_source(source.repo, source.subdir)

    # Catalogs ----------------------------------------------------------

    async def catalog(self, source: Source) -> catalogs.Catalog:
        found = await asyncio.to_thread(self.github.catalog, source)
        self.catalogs[source.repo] = found
        return found

    async def refresh_sources(self) -> list[str]:
        """
        Ask every source what it has now, so that what is available is true
        and installed programs can be told they are out of date. Returns a
        sentence per source that could not be asked - being offline is not an
        error worth stopping for.
        """
        problems: list[str] = []
        for source in list(self.store.config.sources):
            try:
                offers = await self._look(source)
            except ManagerError as err:
                problems.append(f"could not check {source.repo} for updates: {err}")
                continue
            self.store.set_offers(source.repo, source.subdir, offers)
        return problems

    def page_url(self, entry: Entry) -> str | None:
        """
        A page about a program: its own repository if it says one, else its
        folder in the catalog.
        """
        if entry.external is None:
            return None
        stamp = self.stamp_of(entry.external)
        if stamp is None:
            return None
        slug = Path(entry.external.path).name
        catalog = self.catalogs.get(stamp.repo)
        found = catalog.find(slug) if catalog else None
        if found is not None and found.manifest.upstream.startswith("https://"):
            return found.manifest.upstream
        return f"https://github.com/{stamp.repo}/tree/{stamp.branch}/apps/{slug}"

    async def prepare_program(
        self, source: Source, catalog: catalogs.Catalog, app: catalogs.CatalogApp
    ) -> ProgramPrepared:
        plan = await asyncio.to_thread(self.programs.plan, source, catalog, app)
        return ProgramPrepared(source, catalog, app, plan)

    async def install_program(self, prepared: ProgramPrepared, say: Say) -> ExternalApp:
        """
        Put a program on this computer and add it to the list.

        An update keeps what a person set up: the command they edited and the
        environment they filled in.
        """
        app = prepared.app
        await asyncio.to_thread(
            self.programs.install, prepared.source, prepared.catalog, app, say
        )
        folder = self.programs.folder(app.slug)
        existing = next(
            (e for e in self.store.config.externals if Path(e.path) == folder), None
        )
        program = ExternalApp(
            slug=existing.slug if existing else self.store.unused_slug(app.slug),
            name=app.name,
            path=str(folder),
            command=existing.command if existing else "{python} app.py --host {host}",
            description=app.manifest.description,
            env=dict(existing.env) if existing else {},
            python=str(self.programs.venv_python(app.slug))
            if app.needs_packages
            else "",
        )
        self.store.save_external(program)
        return program

    def env_spec(self, app: ExternalApp) -> list[catalogs.EnvVar]:
        if self.stamp_of(app) is None:
            return []
        return self.programs.env_spec(Path(app.path).name)

    def set_env(self, app: ExternalApp, values: dict[str, str]) -> ExternalApp:
        """
        Store the values a person filled in. An empty value means "not set",
        so the program falls back to its own default.
        """
        env = {**app.env}
        for key, value in values.items():
            if value:
                env[key] = value
            else:
                env.pop(key, None)
        updated = replace(app, env=env)
        self.store.save_external(updated)
        return updated

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
        return Prepared(built, staged, source)

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
        self._learn(prepared)

    def _learn(self, prepared: Prepared) -> None:
        """
        Note what an install turned out to be, so that a source whose
        manifest could not be read ahead of time is no longer offered as
        something not yet installed.
        """
        source, manifest = prepared.source, prepared.package.manifest
        if source is None or source.kind != "app":
            return
        self.store.set_offers(
            source.repo,
            source.subdir,
            [
                Offer(
                    source.repo,
                    source.subdir,
                    "",
                    manifest.name,
                    manifest.version,
                    manifest.description,
                    manifest.author,
                    manifest.id,
                )
            ],
        )

    # Using what is there -----------------------------------------------

    async def activate(self, entry: Entry) -> str:
        """
        Start an entry: launch it on the bar, or run it on this computer.
        Returns a sentence about what happened.
        """
        if entry.kind == "available":
            raise ManagerError(
                f"{entry.name} is not installed yet; press i to install it"
            )
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

    async def stop(self, entry: Entry | None, *, by_switch: bool = False) -> str:
        """
        Stop what is running: the selected external app, or whatever the
        bar is running (the bar has one app at a time, so there is no
        choosing).

        The bar is asked to quit first. If it cannot be - old firmware, or it
        tried and failed - this raises `CannotQuitDirectly` and does nothing
        else, because the other way changes what the bar is showing and is
        for the person to agree to. Called again with `by_switch=True` it
        takes that way: Back, and then the switch moved away and to the Apps
        menu.
        """
        if entry is not None and entry.kind == "external" and entry.external:
            if self.launcher.stop(entry.external):
                return f"Stopped {entry.name}"
            raise ManagerError(f"{entry.name} is not running")
        if self.bar is None:
            raise ManagerError(
                "there is no bar to quit an app on (running with --offline)"
            )
        if by_switch:
            await self.bar.leave_by_switch()
            return "Left the app by moving the switch; the bar is on the Apps menu"
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
            if self.stamp_of(entry.external) is not None:
                await asyncio.to_thread(
                    self.programs.remove, Path(entry.external.path).name
                )
                self.store.remove_external(entry.ident)
                return f"Removed {entry.name} and the files it installed"
        self.store.remove_external(entry.ident)
        return f"Forgot {entry.name} (nothing on disk was deleted)"

    # External apps -----------------------------------------------------

    def add_external(
        self, name: str, path: str, command: str, description: str, env: str = ""
    ) -> ExternalApp:
        app = self._external(
            self.store.unused_slug(name), name, path, command, description, env
        )
        self.store.save_external(app)
        return app

    def edit_external(
        self,
        app: ExternalApp,
        name: str,
        path: str,
        command: str,
        description: str,
        env: str = "",
    ) -> ExternalApp:
        updated = self._external(app.slug, name, path, command, description, env)
        # Whatever else the entry carries - the interpreter a catalog install
        # chose - is not on the form and must not be lost by saving it.
        updated = replace(updated, python=app.python)
        self.store.save_external(updated)
        return updated

    @staticmethod
    def _external(
        slug: str, name: str, path: str, command: str, description: str, env: str
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
            env=parse_env(env),
        )
