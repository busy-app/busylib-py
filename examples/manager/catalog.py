"""
A catalog of programs: a repository of folders, each a self-contained program
for a bar that runs on the computer next to it.

The community's catalog at `maxswinkels/busybar-apps` is the model, and this
reads that layout: `apps/<slug>/` holding `app.py`, a `manifest.yaml` that is
the card, optionally a `requirements.txt` and an `.env.example`, and a preview
picture. A program there is started as `python app.py --host <bar>`.

Nothing here talks to the network or the disk. It turns what a listing and a
manifest say into the things the manager shows and installs, and it is
tolerant on purpose: one malformed manifest among fifty must cost one card,
not the catalog.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .model import ManagerError

# A folder name in the catalog; also a folder name here, so it is held to
# something that cannot be a path.
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# Never fetched for an install: the picture for the gallery, the program's own
# tests, and what an editor or an interpreter leaves behind.
_SKIPPED_DIRS = {"tests", "test", "__pycache__", ".venv", "node_modules", ".git"}
_KEPT_DOTFILES = {".env.example"}
ENV_TEMPLATES = (".env.example", "env.example", ".env.sample")

# An install is code that runs on this computer, so it is held to a size that
# no program of this kind comes near.
MAX_INSTALL_BYTES = 40 * 1024 * 1024


@dataclass(frozen=True)
class Manifest:
    """
    The card: what the gallery shows about a program.
    """

    name: str
    author: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    preview: str = ""
    upstream: str = ""


@dataclass(frozen=True)
class CatalogApp:
    slug: str
    manifest: Manifest
    # Relative path -> git blob sha, for everything an install fetches.
    files: Mapping[str, str] = field(default_factory=dict)
    size: int = 0
    requirements: str = ""  # the blob sha of requirements.txt, if there is one
    env_template: str = ""  # the path of the env template, if there is one

    @property
    def name(self) -> str:
        return self.manifest.name or self.slug

    @property
    def needs_packages(self) -> bool:
        return bool(self.requirements)


@dataclass(frozen=True)
class Catalog:
    repo: str
    branch: str
    commit: str
    apps: tuple[CatalogApp, ...] = ()
    # Slugs that were in the listing but could not be read, with why.
    problems: Mapping[str, str] = field(default_factory=dict)

    def find(self, slug: str) -> CatalogApp | None:
        return next((app for app in self.apps if app.slug == slug), None)


# Reading a manifest -----------------------------------------------------------


def _unquote(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        body = raw[1:-1]
        return re.sub(
            r"\\(.)",
            lambda m: {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}.get(
                m.group(1), m.group(1)
            ),
            body,
        )
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    # A plain scalar ends where a comment starts.
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def _flow_list(raw: str) -> list[str]:
    inner = raw.strip()[1:-1]
    items: list[str] = []
    current, quote = "", ""
    for char in inner:
        if quote:
            current += char
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
            current += char
        elif char == ",":
            items.append(current)
            current = ""
        else:
            current += char
    items.append(current)
    return [_unquote(item) for item in items if item.strip()]


def parse_yaml(text: str) -> dict[str, str | list[str]]:
    """
    The small part of YAML a manifest uses: `key: value` lines, quoted or not,
    lists written with dashes or in brackets, `#` comments.

    Not a YAML parser, and says so by refusing what it does not understand
    rather than guessing: a nested mapping raises. PyYAML would be the
    dependency this example does not want for forty-odd five-line files.
    """
    result: dict[str, str | list[str]] = {}
    key: str | None = None
    for number, line in enumerate(text.lstrip("﻿").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        if stripped.startswith("- ") or stripped == "-":
            if key is None or not isinstance(result.get(key), list):
                raise ValueError(f"line {number}: a list item with no list")
            result[key].append(_unquote(stripped[1:]))  # type: ignore[union-attr]
            continue
        if line[:1] in " \t":
            raise ValueError(f"line {number}: nested values are not supported")
        match = re.match(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*))?$", line.rstrip())
        if not match:
            raise ValueError(f"line {number}: not a `key: value` line")
        key, value = match.group(1), match.group(2)
        if value is None or value == "":
            result[key] = []
        elif value.startswith("["):
            result[key] = _flow_list(value)
        elif value[0] in ">|":
            raise ValueError(f"line {number}: block scalars are not supported")
        else:
            result[key] = _unquote(value)
    return result


def parse_manifest(text: str) -> Manifest:
    try:
        data = parse_yaml(text)
    except ValueError as err:
        raise ManagerError(f"the manifest is not readable ({err})") from err

    def text_of(key: str) -> str:
        value = data.get(key, "")
        return value if isinstance(value, str) else ""

    tags = data.get("tags", [])
    name = text_of("name").strip()
    if not name:
        raise ManagerError("the manifest has no name")
    return Manifest(
        name=name,
        author=text_of("author"),
        description=text_of("description"),
        tags=tuple(str(tag) for tag in tags) if isinstance(tags, list) else (),
        preview=text_of("preview"),
        upstream=text_of("repo"),
    )


# What an install fetches --------------------------------------------------------


def safe_relative(path: str) -> PurePosixPath | None:
    """
    A path inside a program's folder, or None if it could leave it.
    """
    if "\\" in path or path.startswith("/"):
        return None
    relative = PurePosixPath(path)
    if ".." in relative.parts or not relative.parts:
        return None
    return relative


def is_runtime(path: str) -> bool:
    """
    Whether an install fetches this file of a program's folder.
    """
    relative = safe_relative(path)
    if relative is None:
        return False
    if any(part in _SKIPPED_DIRS for part in relative.parts[:-1]):
        return False
    name = relative.name
    if len(relative.parts) == 1 and name.lower().startswith("preview."):
        return False
    if name.startswith(".") and name not in _KEPT_DOTFILES:
        return False
    return True


def app_from_listing(
    slug: str, manifest: Manifest, entries: Mapping[str, tuple[str, int]]
) -> CatalogApp:
    """
    A catalog app from its manifest and the files the listing shows in its
    folder (relative path -> (blob sha, size)).
    """
    files = {path: sha for path, (sha, _) in entries.items() if is_runtime(path)}
    size = sum(size for path, (_, size) in entries.items() if path in files)
    env = next((path for path in ENV_TEMPLATES if path in files), "")
    return CatalogApp(
        slug=slug,
        manifest=manifest,
        files=files,
        size=size,
        requirements=files.get("requirements.txt", ""),
        env_template=env,
    )


def git_blob_sha(data: bytes) -> str:
    """
    The sha git gives a file, which is what a listing reports.

    Comparing it with the bytes that arrived is how a download is known to be
    the file the listing was about, and not whatever a cache or a proxy
    held.
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324


# The environment a program reads -------------------------------------------------


@dataclass(frozen=True)
class EnvVar:
    key: str
    example: str = ""
    help: str = ""


def parse_env_template(text: str) -> list[EnvVar]:
    """
    The variables a program says it reads, from its `.env.example`.

    `KEY=value` and `export KEY=value` lines count; a comment directly above
    one, with no blank line between, is its help. The example values are
    documentation (`your-api-key-here`) and are never used as values.
    """
    found: list[EnvVar] = []
    seen: set[str] = set()
    help_lines: list[str] = []
    for line in text.lstrip("﻿").splitlines():
        stripped = line.strip()
        if not stripped:
            help_lines = []
            continue
        if stripped.startswith("#"):
            help_lines.append(stripped.lstrip("#").strip())
            continue
        match = re.match(
            r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped
        )
        if not match:
            help_lines = []
            continue
        key, value = match.groups()
        value = value.strip()
        if value[:1] in "\"'" and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if key not in seen:
            seen.add(key)
            found.append(EnvVar(key, value, " ".join(help_lines)))
        help_lines = []
    return found
