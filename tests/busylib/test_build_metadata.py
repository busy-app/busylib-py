from __future__ import annotations

import importlib
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - only for Python < 3.11
    import tomli as tomllib


def load_pyproject() -> dict[str, object]:
    """
    Прочитать pyproject.toml и вернуть структуру данных.

    Нужен для проверки метаданных сборки без запуска билдов.
    """
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        return tomllib.load(handle)


def test_pyproject_has_required_build_metadata():
    """
    Проверить ключевые метаданные сборки и публикации.

    Гарантирует, что в pyproject указаны обязательные поля проекта.
    """
    data = load_pyproject()
    project = data["project"]
    assert isinstance(project, dict)

    for field in (
        "name",
        "version",
        "description",
        "readme",
        "requires-python",
        "authors",
        "dependencies",
        "urls",
    ):
        assert field in project

    build_system = data["build-system"]
    assert isinstance(build_system, dict)
    assert build_system["build-backend"] == "setuptools.build_meta"
    assert "requires" in build_system
    requires = build_system["requires"]
    assert isinstance(requires, list)
    assert any(item.startswith("setuptools") for item in requires)
    assert any(item.startswith("wheel") for item in requires)


def test_package_layout_is_src_and_importable():
    """
    Проверить src-раскладку и базовую импортируемость пакета.

    Подтверждает, что путь src корректно содержит пакет busylib.
    """
    data = load_pyproject()
    tool = data["tool"]
    assert isinstance(tool, dict)
    setuptools_cfg = tool["setuptools"]
    assert isinstance(setuptools_cfg, dict)
    package_dir = setuptools_cfg["package-dir"]
    assert package_dir == {"": "src"}

    root = Path(__file__).resolve().parents[2]
    package_root = root / "src" / "busylib"
    init_path = package_root / "__init__.py"
    assert init_path.exists()

    sys.path.insert(0, str(root / "src"))
    try:
        module = importlib.import_module("busylib")
    finally:
        sys.path.pop(0)

    assert hasattr(module, "BusyBar")
