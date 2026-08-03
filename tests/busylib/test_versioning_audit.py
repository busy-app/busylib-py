from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from busylib import AsyncBusyBar, BusyBar, versioning

CLIENT_DIR = pathlib.Path(inspect.getfile(BusyBar)).parent


def _declared_request(node: ast.AST) -> tuple[str, str] | None:
    """
    Find the method and path a helper actually passes to `self._request`.

    Returns them with f-string placeholders preserved, so
    `f"/api/busy/profiles/{slot}"` reads as `/api/busy/profiles/{slot}`.
    """
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == "_request"):
            continue
        if len(call.args) < 2:
            continue
        method, path = call.args[0], call.args[1]
        if not isinstance(method, ast.Constant):
            continue
        if isinstance(path, ast.Constant):
            return str(method.value), str(path.value)
        if isinstance(path, ast.JoinedStr):
            rendered = ""
            for part in path.values:
                if isinstance(part, ast.Constant):
                    rendered += str(part.value)
                elif isinstance(part, ast.FormattedValue) and isinstance(
                    part.value, ast.Name
                ):
                    rendered += "{" + part.value.id + "}"
                else:
                    rendered += "{...}"
            return str(method.value), rendered
    return None


def _helpers_with_requests() -> dict[str, tuple[str, str]]:
    """
    Map every client helper to the request it issues, parsed from source.
    """
    found: dict[str, tuple[str, str]] = {}
    for path in sorted(CLIENT_DIR.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name.startswith("_"):
                continue
            request = _declared_request(node)
            if request is not None:
                found.setdefault(node.name, request)
    return found


HELPERS = _helpers_with_requests()


def test_the_audit_finds_helpers_to_check() -> None:
    """
    Guard the parsing itself, so a silent zero doesn't pass the suite.
    """
    assert len(HELPERS) > 30


@pytest.mark.parametrize("name", sorted(HELPERS))
def test_compatibility_metadata_matches_the_actual_request(name: str) -> None:
    """
    A helper's declared path and method match the request it makes.

    Tagging a helper with a neighbouring endpoint's path is invisible at
    runtime but makes the metadata lie, which is the whole point of it.
    """
    metadata = versioning.get_method_compatibility(getattr(BusyBar, name))
    if metadata is None:
        pytest.skip(f"{name} carries no compatibility metadata")

    method, path = HELPERS[name]
    assert metadata["path"] == path
    assert metadata["method"] == method


@pytest.mark.parametrize("name", sorted(HELPERS))
def test_sync_and_async_helpers_are_tagged_alike(name: str) -> None:
    """
    Both clients report the same compatibility metadata.

    Tagging only one leaves `AsyncBusyBar.method_compatibility()` returning
    None for a helper the sync client describes.
    """
    sync = getattr(BusyBar, name, None)
    asyncronous = getattr(AsyncBusyBar, name, None)
    if sync is None or asyncronous is None:
        pytest.skip(f"{name} exists on only one client")

    assert versioning.get_method_compatibility(sync) == (
        versioning.get_method_compatibility(asyncronous)
    )
