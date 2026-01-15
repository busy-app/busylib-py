from __future__ import annotations

from pathlib import Path


def load_readme() -> str:
    """
    Read README.md contents for packaging checks.

    Keeps the PyPI long description aligned with the README text.
    """
    readme_path = Path(__file__).resolve().parents[2] / "README.md"
    return readme_path.read_text(encoding="utf-8")


def test_readme_contains_pypi_badges_and_install():
    """
    Ensure README has PyPI badges and installation commands.

    Validates the long description has discoverable metadata and install steps.
    """
    readme = load_readme()
    assert "https://pypi.org/project/busylib/" in readme
    assert "img.shields.io/pypi/v/busylib" in readme
    assert "img.shields.io/pypi/pyversions/busylib" in readme
    assert "pip install busylib" in readme
    assert "pip install --upgrade busylib" in readme


def test_readme_mentions_async_client_usage():
    """
    Ensure README demonstrates async client usage.

    Confirms the async API is discoverable in the long description.
    """
    readme = load_readme()
    assert "AsyncBusyBar" in readme
    assert "async with AsyncBusyBar" in readme
