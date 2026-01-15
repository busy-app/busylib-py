from __future__ import annotations

from pathlib import Path


def load_workflow() -> str:
    """
    Прочитать workflow публикации в PyPI как текст.

    Держит проверку в тестах без зависимости от YAML-парсера.
    """
    workflow_path = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "pypi-publish.yml"
    )
    return workflow_path.read_text(encoding="utf-8")


def test_pypi_workflow_uses_trusted_publishing():
    """
    Проверить, что workflow использует trusted publishing.

    Требует выдачу id-token и отсутствие использования секрета токена.
    """
    workflow = load_workflow()
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish" in workflow
    assert "PYPI_API_TOKEN" not in workflow
    assert "password:" not in workflow
