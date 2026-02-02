from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - only for Python < 3.11
    import tomli as tomllib


def load_pyproject() -> dict[str, object]:
    """
    Прочитать pyproject.toml и вернуть структуру данных.

    Используется для проверки метаданных без запуска сборки.
    """
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        return tomllib.load(handle)


def test_runtime_dependencies_do_not_include_test_tools():
    """
    Проверить, что тестовые пакеты не входят в runtime-зависимости.

    Это гарантирует, что установка библиотеки не тянет pytest.
    """
    data = load_pyproject()
    project = data["project"]
    assert isinstance(project, dict)
    dependencies = project["dependencies"]
    assert isinstance(dependencies, list)
    for requirement in ("pytest", "pytest-asyncio"):
        assert all(not item.startswith(f"{requirement}") for item in dependencies)


def test_dev_dependencies_include_pytest_asyncio_and_tomli():
    """
    Проверить, что dev-зависимости включают pytest-asyncio и tomli.

    Это нужно для запуска тестов на Python 3.10+ и корректного asyncio режима.
    """
    data = load_pyproject()
    dep_groups = data["dependency-groups"]
    assert isinstance(dep_groups, dict)
    dev_group = dep_groups["dev"]
    assert isinstance(dev_group, list)
    assert any(item.startswith("pytest-asyncio") for item in dev_group)
    assert any(item.startswith("tomli") for item in dev_group)
