import tomllib
from pathlib import Path


def test_examples_dependency_group_includes_hltv() -> None:
    """
    Проверить, что группа examples содержит python-hltv и зависимости.

    Это гарантирует воспроизводимую установку примера.
    """
    pyproject = Path("pyproject.toml").read_bytes()
    data = tomllib.loads(pyproject.decode("utf-8"))
    groups = data.get("dependency-groups", {})
    examples = groups.get("examples", [])

    assert "hltv>=0.2" in examples
    assert "beautifulsoup4>=4.12" in examples
    assert "lxml>=5" in examples
