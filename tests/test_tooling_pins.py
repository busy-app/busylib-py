from __future__ import annotations

import pathlib
import re
import sys

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"

# The hook repositories whose revision has to match a pin in the dev group.
# Anything not listed here - pre-commit-hooks, for instance - carries no
# counterpart in pyproject.toml and is left alone.
HOOK_REPO_TO_PACKAGE = {
    "https://github.com/astral-sh/ruff-pre-commit": "ruff",
    "https://github.com/tox-dev/pyproject-fmt": "pyproject-fmt",
    "https://github.com/RobertCraigie/pyright-python": "pyright",
}


def _pinned_dev_versions() -> dict[str, str]:
    """
    Read the exact-pinned dev dependencies out of pyproject.toml.
    """
    data = tomllib.loads(PYPROJECT.read_text())
    pins: dict[str, str] = {}
    for entry in data["dependency-groups"]["dev"]:
        name, separator, version = entry.partition("==")
        if separator:
            pins[name.strip()] = version.strip()
    return pins


def _hook_revisions() -> dict[str, str]:
    """
    Map each pre-commit hook repository to the revision it is pinned at.

    Parsed with a regex rather than a YAML library because the project has no
    YAML dependency, and this file is a flat list of `repo`/`rev` pairs.
    """
    text = PRE_COMMIT.read_text()
    pairs = re.findall(
        r"^\s*-\s*repo:\s*(\S+)\s*\n\s*rev:\s*(\S+)\s*$", text, flags=re.MULTILINE
    )
    return dict(pairs)


def test_the_parsing_finds_something() -> None:
    """
    Guard the parsers, so a silent empty result cannot pass the checks below.
    """
    assert _pinned_dev_versions()
    assert set(_hook_revisions()) >= set(HOOK_REPO_TO_PACKAGE)


@pytest.mark.parametrize("repo,package", sorted(HOOK_REPO_TO_PACKAGE.items()))
def test_linters_are_pinned_alike_in_both_files(repo: str, package: str) -> None:
    """
    A linter is the same version for pre-commit and for CI.

    When the two drift, CI installs a different linter than the hooks do and
    unrelated pull requests go red - a ruff release once failed main itself
    this way. Dependabot now proposes each bump as two pull requests, one per
    file, and this is what stops one of them landing alone.
    """
    revision = _hook_revisions()[repo]
    pinned = _pinned_dev_versions().get(package)

    assert pinned is not None, f"{package} is not pinned in pyproject.toml"
    # Compared as version numbers, not strings: pyproject-fmt normalizes the
    # specifiers it writes, so 2.28.0 becomes ==2.28 in pyproject.toml while
    # the hook revision stays at the release tag v2.28.0.
    assert _release_parts(revision.lstrip("v")) == _release_parts(pinned), (
        f"{package}: .pre-commit-config.yaml has {revision}, "
        f"pyproject.toml pins {pinned}"
    )


def _release_parts(version: str) -> tuple[int, ...]:
    """
    Split a version into numbers, ignoring trailing zeros.

    `2.28` and `2.28.0` are the same release written two ways.
    """
    parts = [int(part) for part in version.split(".") if part.isdigit()]
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts)
