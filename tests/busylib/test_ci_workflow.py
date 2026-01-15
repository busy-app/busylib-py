from __future__ import annotations

from pathlib import Path


def load_ci_workflow() -> str:
    """
    Прочитать CI workflow как текст.

    Упрощает проверку матрицы без YAML-зависимостей.
    """
    workflow_path = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    )
    return workflow_path.read_text(encoding="utf-8")


def test_ci_workflow_has_python_matrix():
    """
    Проверить наличие матрицы Python 3.10-3.13 в CI.

    Подтверждает, что сборка гоняется на всех поддерживаемых версиях.
    """
    workflow = load_ci_workflow()
    for version in ("3.10", "3.11", "3.12", "3.13"):
        assert version in workflow
    assert "python-version" in workflow
    assert "pytest -q" in workflow
