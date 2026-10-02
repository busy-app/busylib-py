"""
Whether the Node.js on this computer can build a BUSY app.

The engine that runs the apps' tooling works on Node before 26 and not on
anything newer, so a computer that has just upgraded Node fails in a way that
looks like the app's fault: a build that dies somewhere in its dependencies.
Saying so up front is the difference between a reason and a puzzle.

The app's own `package.json` can say more (`"node": ">=24 <26"`), and that is
honoured too. Only the parts of npm's range syntax that people actually write
in `engines` are understood; a range this cannot read never blocks a build,
because refusing on a guess is worse than letting the build speak.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .model import ManagerError

Version = tuple[int, int, int]

# The first Node release the tooling does not work on.
FIRST_UNSUPPORTED = 26


def parse_version(text: str) -> Version | None:
    """
    "v25.2.1" -> (25, 2, 1); None if it is not a version.
    """
    match = re.match(r"^v?(\d+)(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?", text.strip())
    if not match:
        return None
    parts = [
        0 if part is None or part in "xX*" else int(part) for part in match.groups()
    ]
    return (parts[0], parts[1], parts[2])


def _bounds(token: str) -> list[tuple[str, Version]] | None:
    """
    One comparator as lower and upper bounds, or None if unreadable.

    Each bound is an operator ("ge" or "lt") and a version, so that every
    comparator, caret and tilde included, is the same two checks.
    """
    token = token.strip()
    if token in ("", "*", "x", "X"):
        return []
    match = re.match(r"^(>=|<=|>|<|=|\^|~)?\s*(v?[\dxX*.]+)$", token)
    if not match:
        return None
    operator, raw = match.groups()
    version = parse_version(raw)
    if version is None:
        return None
    major, minor, patch = version
    wildcards = sum(part in "xX*" for part in raw.lstrip("v").split("."))
    given = len(raw.lstrip("v").split(".")) - wildcards  # components stated

    if operator == ">=":
        return [("ge", version)]
    if operator == ">":
        # Greater than 24 means 25 and up; greater than 24.1 means 24.2 and up.
        if given <= 1:
            return [("ge", (major + 1, 0, 0))]
        if given == 2:
            return [("ge", (major, minor + 1, 0))]
        return [("ge", (major, minor, patch + 1))]
    if operator == "<":
        return [("lt", version)]
    if operator == "<=":
        if given <= 1:
            return [("lt", (major + 1, 0, 0))]
        if given == 2:
            return [("lt", (major, minor + 1, 0))]
        return [("lt", (major, minor, patch + 1))]
    if operator == "^":
        if major > 0:
            return [("ge", version), ("lt", (major + 1, 0, 0))]
        if minor > 0:
            return [("ge", version), ("lt", (0, minor + 1, 0))]
        return [("ge", version), ("lt", (0, 0, patch + 1))]
    if operator == "~":
        if given <= 1:
            return [("ge", version), ("lt", (major + 1, 0, 0))]
        return [("ge", version), ("lt", (major, minor + 1, 0))]

    # No operator, or "=": exactly that version, or that whole line (24, 24.x).
    if given <= 1:
        return [("ge", (major, 0, 0)), ("lt", (major + 1, 0, 0))]
    if given == 2:
        return [("ge", (major, minor, 0)), ("lt", (major, minor + 1, 0))]
    return [("ge", version), ("lt", (major, minor, patch + 1))]


def satisfies(version: Version, wanted: str) -> bool | None:
    """
    Whether `version` is in an npm range; None when the range cannot be read.
    """
    alternatives = [part for part in wanted.split("||")] or [wanted]
    readable = False
    for alternative in alternatives:
        # "24 - 25" style ranges are rare in engines; not worth reading.
        if " - " in alternative:
            continue
        bounds: list[tuple[str, Version]] = []
        ok = True
        for token in alternative.split():
            parsed = _bounds(token)
            if parsed is None:
                ok = False
                break
            bounds += parsed
        if not ok:
            continue
        readable = True
        if all(
            version >= bound if kind == "ge" else version < bound
            for kind, bound in bounds
        ):
            return True
    return False if readable else None


def engines_range(source_dir: Path) -> str:
    """
    What the app's package.json asks of Node, or "" if it asks nothing.
    """
    try:
        data = json.loads((source_dir / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    engines = data.get("engines") if isinstance(data, dict) else None
    wanted = engines.get("node") if isinstance(engines, dict) else None
    return wanted if isinstance(wanted, str) else ""


def check(source_dir: Path, version_text: str) -> None:
    """
    Raise a ManagerError saying why this Node cannot build this app, if so.

    `version_text` is what `node --version` printed.
    """
    version = parse_version(version_text)
    if version is None:
        return  # Cannot tell; let the build speak.

    shown = ".".join(str(part) for part in version)
    wanted = engines_range(source_dir)
    fix = (
        "Use Node 24 or 25 (a version manager such as nvm or fnm switches "
        "between them), or install a released version of the app, which needs "
        "no Node at all."
    )

    if version[0] >= FIRST_UNSUPPORTED:
        asks = f" (this app asks for {wanted})" if wanted else ""
        raise ManagerError(
            f"Node.js {shown} is too new to build BUSY apps: the tooling "
            f"works on Node before {FIRST_UNSUPPORTED}{asks}. {fix}"
        )
    if wanted and satisfies(version, wanted) is False:
        raise ManagerError(
            f"Node.js {shown} cannot build this app: its package.json asks "
            f"for {wanted}. {fix}"
        )


def installed() -> str | None:
    """
    Where Node is, if it is.
    """
    return shutil.which("node")
