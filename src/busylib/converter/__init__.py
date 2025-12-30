from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from . import audio, image, video

logger = logging.getLogger(__name__)

ConverterFn = Callable[[str, bytes], tuple[str, bytes] | None]


def _registry() -> dict[str, ConverterFn]:
    return {
        ".mp3": audio.convert,
        ".ogg": audio.convert,
        ".aac": audio.convert,
        ".m4a": audio.convert,
        ".flac": audio.convert,
        ".wav": audio.convert,
        ".jpg": image.convert,
        ".jpeg": image.convert,
        ".png": image.convert,
        ".bmp": image.convert,
        ".tif": image.convert,
        ".tiff": image.convert,
        ".gif": video.convert,
        ".webp": video.convert,
        ".mov": video.convert,
        ".mp4": video.convert,
        ".mkv": video.convert,
        ".avi": video.convert,
        ".webm": video.convert,
    }


def convert_for_storage(path: str, data: bytes) -> tuple[str, bytes]:
    suffix = Path(path).suffix.lower()
    converter = _registry().get(suffix)
    if not converter:
        return path, data
    try:
        result = converter(path, data)
        if result is None:
            return path, data
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("Conversion failed for %s: %s", path, exc)
        return path, data
