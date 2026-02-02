from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def convert(path: str, data: bytes) -> tuple[str, bytes] | None:
    """
    Reject video/animation conversion until the pipeline is implemented.

    Logs the file name to make the unsupported case visible to users.
    """
    logger.info("Video conversion not implemented for %s", Path(path).name)
    raise NotImplementedError("Video/animation conversion is not supported yet")
