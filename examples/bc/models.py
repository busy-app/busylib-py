from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Entry(BaseModel):
    """
    File entry for listing panels.

    Stores name, type, size, and an optional resolved path for previews.
    """

    model_config = ConfigDict(validate_assignment=True)

    name: str
    is_dir: bool
    size: int
    path: str | None = None


def human_size(value: int) -> str:
    """
    Format byte size as a human-readable string.

    Uses binary units with one decimal for non-bytes and keeps bytes as integers.
    """
    units = ["B", "K", "M", "G", "T"]
    size = float(value)
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.1f}{units[unit]}" if unit else f"{int(size)}B"
