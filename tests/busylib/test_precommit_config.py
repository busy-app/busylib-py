from __future__ import annotations

from pathlib import Path


def test_precommit_config_contains_core_hooks() -> None:
    """
    Ensure pre-commit config exists and includes core quality hooks.
    """
    config_path = Path(".pre-commit-config.yaml")
    assert config_path.exists()
    data = config_path.read_text(encoding="utf-8")
    assert "ruff-pre-commit" in data
    assert "id: ruff" in data
    assert "id: ruff-format" in data
    assert "pycqa/isort" in data
    assert "id: isort" in data
    assert "tox-dev/pyproject-fmt" in data
    assert "id: pyproject-fmt" in data
