"""
Programs from a catalog, installed on this computer.

A program is a folder of files that runs on the computer next to the bar, so
installing one is putting those files somewhere, with whatever packages they
need, and being able to say later whether they are out of date and to remove
them without removing anything else.

Three rules shape the code. Every file is checked against the sha the listing
gave it, so what lands is what was listed. A folder is replaced by building
the new one beside it and swapping, so an install that fails halfway leaves
the old program working. And the manager deletes only folders it installed,
directly under its own root, never following a link.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import catalog as catalogs
from .github import GitHub
from .model import ManagerError, Source
from .package import Runner, run_command

STAMP = ".busy-apps.json"
VENVS = ".venvs"

Say = Callable[[str], None]


@dataclass
class Installed:
    """
    What is known about a program the manager put on this computer: where it
    came from, which commit, and the sha of every file it wrote.
    """

    repo: str
    branch: str
    commit: str
    files: dict[str, str] = field(default_factory=dict)
    # The sha of the requirements the program's packages were installed for.
    requirements: str = ""
    installed_at: float = 0.0
    updated_at: float = 0.0


@dataclass(frozen=True)
class Plan:
    """
    What an install will do, so a person can say yes knowing.
    """

    files: int
    size: int
    packages: tuple[str, ...]
    replaces: Installed | None
    folder: Path


def needs_update(stamp: Installed, app: catalogs.CatalogApp) -> bool:
    """
    Whether the catalog's copy of a program differs from the installed one.

    Compared by the files' shas rather than by commit: the catalog's commit
    moves whenever any program in it changes, and a program must not be
    reported out of date because its neighbour was edited.
    """
    return dict(app.files) != stamp.files


class Programs:
    """
    The folder where installed programs live, and what can be done to it.
    """

    def __init__(
        self,
        root: Path,
        github: GitHub,
        *,
        run: Runner = run_command,
        python: str = sys.executable,
    ) -> None:
        self.root = root
        self.github = github
        self.run = run
        self.python = python

    # Where things are --------------------------------------------------

    def folder(self, slug: str) -> Path:
        """
        The folder for a slug, which is always a direct child of the root.
        """
        if not catalogs.SLUG.match(slug):
            raise ManagerError(
                f"{slug!r} is not a name a program can be installed under"
            )
        return self.root / slug

    def venv_python(self, slug: str) -> Path:
        venv = self.root / VENVS / slug
        return venv / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )

    def stamp(self, slug: str) -> Installed | None:
        try:
            data = json.loads((self.folder(slug) / STAMP).read_text(encoding="utf-8"))
            return Installed(**data)
        except (OSError, ValueError, TypeError, ManagerError):
            return None

    def installed(self) -> dict[str, Installed]:
        found: dict[str, Installed] = {}
        if not self.root.is_dir():
            return found
        for child in sorted(self.root.iterdir()):
            if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
                continue
            stamp = self.stamp(child.name)
            if stamp is not None:
                found[child.name] = stamp
        return found

    def env_spec(self, slug: str) -> list[catalogs.EnvVar]:
        """
        The variables the installed program says it reads.
        """
        for name in catalogs.ENV_TEMPLATES:
            template = self.folder(slug) / name
            try:
                return catalogs.parse_env_template(template.read_text(encoding="utf-8"))
            except OSError:
                continue
        return []

    # Installing --------------------------------------------------------

    def plan(
        self, source: Source, catalog: catalogs.Catalog, app: catalogs.CatalogApp
    ) -> Plan:
        if app.size > catalogs.MAX_INSTALL_BYTES:
            raise ManagerError(
                f"{app.name} is {app.size // (1024 * 1024)} MiB, more than a "
                f"program of this kind should be ({catalogs.MAX_INSTALL_BYTES // (1024 * 1024)} MiB)"
            )
        packages: tuple[str, ...] = ()
        if app.needs_packages:
            text = self._fetch(
                source, catalog, app, "requirements.txt", app.requirements
            ).decode("utf-8", errors="replace")
            packages = tuple(
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            )
        return Plan(
            files=len(app.files),
            size=app.size,
            packages=packages,
            replaces=self.stamp(app.slug),
            folder=self.folder(app.slug),
        )

    def _fetch(
        self,
        source: Source,
        catalog: catalogs.Catalog,
        app: catalogs.CatalogApp,
        path: str,
        sha: str,
    ) -> bytes:
        data = self.github.raw(
            source.repo, catalog.commit, f"apps/{app.slug}/{path}", 32 * 1024 * 1024
        )
        if catalogs.git_blob_sha(data) != sha:
            raise ManagerError(
                f"{path} of {app.name} is not the file the listing described; "
                "nothing was installed"
            )
        return data

    def install(
        self,
        source: Source,
        catalog: catalogs.Catalog,
        app: catalogs.CatalogApp,
        say: Say = lambda line: None,
    ) -> Installed:
        folder = self.folder(app.slug)
        previous = self.stamp(app.slug)
        if previous is not None and previous.repo != source.repo:
            raise ManagerError(
                f"{app.slug} is already installed from {previous.repo}; remove it "
                f"first to install the one from {source.repo}"
            )
        if previous is None and folder.exists():
            raise ManagerError(
                f"{folder} already exists and was not installed by this manager; "
                "move it away first"
            )

        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".staging-{app.slug}-{int(time.time())}"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        try:
            say(f"downloading {len(app.files)} file(s), {max(app.size // 1024, 1)} KiB")

            def fetch(item: tuple[str, str]) -> tuple[str, bytes]:
                path, sha = item
                return path, self._fetch(source, catalog, app, path, sha)

            with ThreadPoolExecutor(max_workers=6) as pool:
                for path, data in pool.map(fetch, sorted(app.files.items())):
                    relative = catalogs.safe_relative(path)
                    if relative is None:  # is_runtime already filters; belt and braces
                        raise ManagerError(f"refusing the path {path!r}")
                    target = staging / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)

            self._packages(app, previous, staging, say)
            self._swap(staging, folder)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        now = time.time()
        stamp = Installed(
            repo=source.repo,
            branch=catalog.branch,
            commit=catalog.commit,
            files=dict(app.files),
            requirements=app.requirements,
            installed_at=previous.installed_at if previous else now,
            updated_at=now,
        )
        (folder / STAMP).write_text(
            json.dumps(asdict(stamp), indent=2), encoding="utf-8"
        )
        say(f"installed {app.name} in {folder}")
        return stamp

    def _packages(
        self,
        app: catalogs.CatalogApp,
        previous: Installed | None,
        staging: Path,
        say: Say,
    ) -> None:
        """
        Give the program its own packages, in an environment of its own.

        Kept beside the programs and not inside them: an environment cannot be
        moved, and replacing a program's folder is a move. A program whose
        requirements have not changed keeps the environment it has.
        """
        if not app.needs_packages:
            return
        venv = self.root / VENVS / app.slug
        interpreter = self.venv_python(app.slug)
        fresh = not interpreter.exists()
        if (
            not fresh
            and previous is not None
            and previous.requirements == app.requirements
        ):
            say("packages unchanged")
            return

        if fresh:
            say("creating an environment for its packages")
            venv.parent.mkdir(parents=True, exist_ok=True)
            code, output = self.run([self.python, "-m", "venv", str(venv)], self.root)
            if code != 0:
                shutil.rmtree(venv, ignore_errors=True)
                raise ManagerError(f"could not create an environment:\n{_tail(output)}")
        say("installing its packages")
        code, output = self.run(
            [
                str(interpreter),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(staging / "requirements.txt"),
            ],
            staging,
        )
        if code != 0:
            if fresh:
                shutil.rmtree(venv, ignore_errors=True)
            raise ManagerError(f"installing its packages failed:\n{_tail(output)}")

    def _swap(self, staging: Path, folder: Path) -> None:
        """
        Put the new folder where the old one is, so that at no moment is there
        half a program.
        """
        trash: Path | None = None
        if folder.exists():
            trash = self.root / f".trash-{folder.name}-{int(time.time())}"
            folder.rename(trash)
        try:
            staging.rename(folder)
        except OSError as err:
            if trash is not None:
                trash.rename(folder)
            raise ManagerError(f"could not put the program in place: {err}") from err
        if trash is not None:
            shutil.rmtree(trash, ignore_errors=True)

    # Removing ----------------------------------------------------------

    def remove(self, slug: str) -> None:
        """
        Delete a program this manager installed, and its packages.

        Only a direct child of the root, only one that carries the manager's
        stamp, and never through a link: a name that arrives from a settings
        file is not a license to delete whatever it points at.
        """
        folder = self.folder(slug)
        if folder.is_symlink() or folder.parent.resolve() != self.root.resolve():
            raise ManagerError(f"{folder} is not a program this manager installed")
        if self.stamp(slug) is None:
            raise ManagerError(
                f"{folder} was not installed by this manager, so it is left alone"
            )
        shutil.rmtree(folder)
        venv = self.root / VENVS / slug
        if venv.exists() and not venv.is_symlink():
            shutil.rmtree(venv, ignore_errors=True)


def _tail(output: str, lines: int = 10) -> str:
    return "\n".join(output.strip().splitlines()[-lines:])
