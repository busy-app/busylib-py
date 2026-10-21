"""
Turning what a source gives us into a package the bar accepts.

The bar's installer is picky in one way that matters: it unpacks the archive
and looks at the *first level* for a folder that loads as an application,
taking the first that does. So a package is a tgz with exactly one folder in
it, `<app id>/`, holding `appmeta/manifest.json` and everything that file
refers to.

Packages come from three places - a release asset, a folder that was just
built, a hand-made archive - and they arrive in whatever layout their author
liked. Everything is therefore read once, checked, and written again in the
one layout the bar wants, deterministically. That also drops the junk
operating systems leave in folders.
"""

from __future__ import annotations

import fnmatch
import gzip
import io
import json
import shutil
import subprocess
import tarfile
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath

from . import node
from .model import MAX_PACKAGE_BYTES, AppManifest, ManagerError, Package

MANIFEST = "appmeta/manifest.json"

# Where an application keeps its manifest in a source tree, in the order
# looked: the layout `busy-cli` scaffolds, then the layout of a built folder.
SOURCE_MANIFESTS = ("src/appmeta/manifest.json", "appmeta/manifest.json")

# What a person's computer leaves behind and the bar has no use for.
_JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
_JUNK_PREFIXES = ("._",)
_JUNK_DIRS = {"__MACOSX", ".git", "node_modules"}

# An archive can claim to hold far more than it weighs. This is the most the
# manager will read out of one, however small the download was.
_MAX_UNPACKED = 4 * MAX_PACKAGE_BYTES

Runner = Callable[[list[str], Path], "tuple[int, str]"]

NO_NODE = (
    "building from source needs Node.js (before version 26) and pnpm, and one "
    "of them was not found. Install them (https://nodejs.org, then "
    "`npm install -g pnpm`), or pick a released version, which needs nothing."
)


def _is_junk(path: PurePosixPath) -> bool:
    if any(part in _JUNK_DIRS for part in path.parts):
        return True
    name = path.name
    return name in _JUNK_NAMES or name.startswith(_JUNK_PREFIXES)


def _clean(name: str) -> PurePosixPath:
    """
    An archive member's name, refused if it could leave its folder.
    """
    path = PurePosixPath(name.replace("\\", "/"))
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(part.endswith(":") for part in path.parts[:1])
    ):
        raise ManagerError(f"the archive holds an unsafe path: {name!r}")
    return PurePosixPath(*[part for part in path.parts if part != "."])


def parse_manifest(data: bytes) -> AppManifest:
    try:
        return AppManifest.from_json(json.loads(data.decode("utf-8-sig")))
    except (ValueError, UnicodeDecodeError) as err:
        raise ManagerError(f"the manifest is not valid JSON ({err})") from err


def _write(entries: Iterator[tuple[PurePosixPath, bytes]], root: str) -> bytes:
    """
    A tgz of `entries` under `root/`, the same bytes for the same input.
    """
    buffer = io.BytesIO()
    # mtime=0 in both the gzip header and the members: a package built twice
    # from one tree is then identical, which makes "did anything change"
    # answerable with a hash.
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar:
            folders: set[PurePosixPath] = set()
            for path, content in sorted(entries, key=lambda item: item[0].as_posix()):
                full = PurePosixPath(root) / path
                for parent in reversed(full.parents):
                    if parent == PurePosixPath(".") or parent in folders:
                        continue
                    folders.add(parent)
                    info = tarfile.TarInfo(parent.as_posix())
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    tar.addfile(info)
                info = tarfile.TarInfo(full.as_posix())
                info.size = len(content)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(content))
    data = buffer.getvalue()
    if len(data) > MAX_PACKAGE_BYTES:
        raise ManagerError(
            f"the package is {len(data) // (1024 * 1024)} MiB and the bar takes "
            f"{MAX_PACKAGE_BYTES // (1024 * 1024)} MiB at most"
        )
    return data


def _from_entries(entries: dict[PurePosixPath, bytes]) -> Package:
    """
    A package from files keyed by their path inside the application.
    """
    manifest_bytes = entries.get(PurePosixPath(MANIFEST))
    if manifest_bytes is None:
        raise ManagerError(f"there is no {MANIFEST} in it")
    manifest = parse_manifest(manifest_bytes)
    return Package(manifest, _write(iter(entries.items()), manifest.id))


def normalize_package(data: bytes) -> Package:
    """
    Check an archive that claims to be an application, and rewrite it in the
    layout the bar's installer wants.

    Nothing is extracted to disk: a package comes from the internet, and
    reading it in memory with every name vetted is the way not to find out
    what a hostile one would have done.
    """
    if len(data) > MAX_PACKAGE_BYTES:
        raise ManagerError("the download is larger than the bar accepts")
    try:
        archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except (tarfile.TarError, EOFError, OSError) as err:
        raise ManagerError(f"that is not a tar or tgz archive ({err})") from err

    files: dict[PurePosixPath, bytes] = {}
    unpacked = 0
    with archive:
        for member in archive:
            if member.isdir():
                _clean(member.name)
                continue
            if not member.isfile():
                # A link or a device node inside an application is either a
                # mistake or an attack, and neither belongs on the bar.
                raise ManagerError(
                    f"the archive holds a link or device: {member.name!r}"
                )
            path = _clean(member.name)
            unpacked += member.size
            if unpacked > _MAX_UNPACKED:
                raise ManagerError("the archive unpacks to far more than it should")
            if _is_junk(path):
                continue
            extracted = archive.extractfile(member)
            if extracted is not None:
                files[path] = extracted.read()

    roots = {
        path.parent.parent
        for path in files
        if path.parts[-2:] == ("appmeta", "manifest.json") and len(path.parts) <= 3
    }
    if not roots:
        raise ManagerError(f"there is no {MANIFEST} in it, so it is not an application")
    if len(roots) > 1:
        names = ", ".join(sorted(str(root) or "(top level)" for root in roots))
        raise ManagerError(f"it holds more than one application: {names}")
    (root,) = roots

    return _from_entries(
        {
            path.relative_to(root): content
            for path, content in files.items()
            if path == root or root in path.parents or str(root) == "."
        }
    )


def pack_directory(app_dir: Path) -> Package:
    """
    A package from a folder that already looks like an application:
    `appmeta/manifest.json` at its top, as `busy-cli build` leaves it.
    """
    if not (app_dir / MANIFEST).is_file():
        raise ManagerError(f"{app_dir} has no {MANIFEST}")
    entries: dict[PurePosixPath, bytes] = {}
    total = 0
    for path in sorted(app_dir.rglob("*")):
        relative = PurePosixPath(path.relative_to(app_dir).as_posix())
        if not path.is_file() or path.is_symlink() or _is_junk(relative):
            continue
        total += path.stat().st_size
        if total > _MAX_UNPACKED:
            raise ManagerError(f"{app_dir} is far larger than an application should be")
        entries[relative] = path.read_bytes()
    return _from_entries(entries)


def find_manifest(source_dir: Path, hint: str = "") -> tuple[Path, AppManifest]:
    """
    The manifest of the application in a source tree, and where it was.
    """
    candidates = [hint] if hint else list(SOURCE_MANIFESTS)
    for candidate in candidates:
        path = source_dir / candidate
        if path.is_file():
            return path, parse_manifest(path.read_bytes())
    raise ManagerError(
        f"no manifest in the source (looked for {', '.join(candidates)}); "
        "set the manifest path on the source"
    )


def safe_extract(archive_bytes: bytes, destination: Path) -> Path:
    """
    Unpack a source tarball from GitHub and return the folder it holds.

    Unlike `normalize_package`, this does write to disk, because a build
    needs files. Every member is checked first, and anything that is not a
    plain file or folder is skipped rather than followed.
    """
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    try:
        archive = tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*")
    except (tarfile.TarError, EOFError, OSError) as err:
        raise ManagerError(f"the source download is not an archive ({err})") from err

    tops: set[str] = set()
    unpacked = 0
    with archive:
        for member in archive:
            path = _clean(member.name)
            if not path.parts:
                continue
            tops.add(path.parts[0])
            target = (base / Path(*path.parts)).resolve()
            if base not in target.parents and target != base:
                raise ManagerError(f"the source holds an unsafe path: {member.name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                unpacked += member.size
                if unpacked > _MAX_UNPACKED:
                    raise ManagerError("the source unpacks to far more than it should")
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                if extracted is not None:
                    target.write_bytes(extracted.read())
    if len(tops) != 1:
        return destination
    return destination / next(iter(tops))


def run_command(argv: list[str], cwd: Path) -> tuple[int, str]:
    """
    Run a build step and return its exit code and everything it said.
    """
    try:
        done = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 1, "timed out after 15 minutes"
    except OSError as err:
        return 1, str(err)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def build_tool(source_dir: Path) -> str:
    """
    Which package manager builds this tree, or why none can.
    """
    wants_pnpm = (source_dir / "pnpm-lock.yaml").exists() or not (
        source_dir / "package-lock.json"
    ).exists()
    for name in ("pnpm", "npm") if wants_pnpm else ("npm", "pnpm"):
        found = shutil.which(name)
        if found:
            return found
    raise ManagerError(NO_NODE)


def build_from_source(
    source_dir: Path,
    *,
    manifest_hint: str = "",
    run: Runner = run_command,
    say: Callable[[str], None] = lambda line: None,
) -> Package:
    """
    Install a source tree's dependencies, build it, and package the result.

    The application's id is read from its source manifest first and used to
    pick the build output: a `dist` folder keeps every application it ever
    built, so "the folder in dist" can be the wrong one.
    """
    _, source_manifest = find_manifest(source_dir, manifest_hint)
    tool = build_tool(source_dir)
    # Before installing anything: the packages are downloaded for a Node that
    # may not be able to use them, and the failure that follows says nothing
    # about Node.
    node_path = node.installed()
    if node_path is None:
        raise ManagerError(NO_NODE)
    code, printed = run([node_path, "--version"], source_dir)
    if code == 0:
        node.check(source_dir, printed)
    name = Path(tool).stem.lower()
    if name == "pnpm":
        install = [tool, "install", "--frozen-lockfile"]
    else:
        # `npm ci` is the exact-lockfile install; without a lockfile there
        # is nothing to be exact about.
        has_lock = (source_dir / "package-lock.json").exists()
        install = [tool, "ci" if has_lock else "install"]

    for label, argv in (
        ("installing dependencies", install),
        ("building", [tool, "run", "build"]),
    ):
        say(f"{label}: {name} {' '.join(argv[1:])}")
        code, output = run(argv, source_dir)
        if code != 0:
            tail = "\n".join(output.strip().splitlines()[-12:])
            raise ManagerError(f"{label} failed (exit {code}):\n{tail}")

    built = source_dir / "dist" / source_manifest.id
    if not built.is_dir():
        raise ManagerError(
            f"the build finished but dist/{source_manifest.id} is not there; "
            "does the build script write it?"
        )
    say(f"packaging dist/{source_manifest.id}")
    return pack_directory(built)


def matches(name: str, pattern: str) -> bool:
    """
    Whether a release file is the package, by the source's pattern.

    Several patterns can be given, separated by commas.
    """
    return any(
        fnmatch.fnmatch(name.lower(), item.strip().lower())
        for item in pattern.split(",")
        if item.strip()
    )
