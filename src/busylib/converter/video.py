from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def convert(path: str, data: bytes) -> tuple[str, bytes] | None:
    # Video to anim is not implemented yet; keep original bytes.
    logger.info("Video conversion not implemented for %s, uploading as-is", Path(path).name)
    return None
