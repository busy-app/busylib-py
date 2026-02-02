from __future__ import annotations

from pathlib import Path


def load_manifest() -> list[str]:
    """
    Read MANIFEST.in and return non-empty lines.

    Keeps packaging rules visible to tests without invoking build tools.
    """
    manifest_path = Path(__file__).resolve().parents[2] / "MANIFEST.in"
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def test_manifest_excludes_egg_info():
    """
    Ensure packaging rules exclude generated egg-info artifacts.

    This prevents accidentally shipping build metadata in sdists.
    """
    manifest_lines = load_manifest()
    expected_rules = {"prune *.egg-info", "prune **/*.egg-info"}
    missing = expected_rules.difference(set(manifest_lines))
    assert not missing, f"Missing MANIFEST rules: {sorted(missing)}"
