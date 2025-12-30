from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


def convert(path: str, data: bytes) -> tuple[str, bytes] | None:
    suffix = Path(path).suffix.lower()
    if suffix == ".png":
        return None

    try:
        image = Image.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to open image: {exc}") from exc

    output = io.BytesIO()
    image.save(output, format="PNG")
    new_path = str(Path(path).with_suffix(".png"))
    logger.debug("Converted %s to PNG", path)
    return new_path, output.getvalue()
