from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .. import exceptions
from . import audio, image, video

logger = logging.getLogger(__name__)

ConverterFn = Callable[[str, bytes], tuple[str, bytes] | None]


def _registry() -> dict[str, ConverterFn]:
    """
    Build the extension-to-converter mapping.

    Centralizes format support for storage conversion.
    """
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
        ".webp": image.convert,
        ".mov": video.convert,
        ".mp4": video.convert,
        ".mkv": video.convert,
        ".avi": video.convert,
        ".webm": video.convert,
    }


def convert_for_storage(path: str, data: bytes) -> tuple[str, bytes]:
    """
    Convert a file payload to a device-ready format when supported.

    Unknown extensions are passed through unchanged. Known extensions must
    convert successfully, otherwise a domain-level conversion error is raised.
    """
    suffix = Path(path).suffix.lower()
    converter = _registry().get(suffix)
    if not converter:
        return path, data
    try:
        result = converter(path, data)
        if result is None:
            raise exceptions.BusyBarConversionError(
                "Converter returned no output",
                path=path,
            )
        return result
    except exceptions.BusyBarConversionError:
        raise
    except NotImplementedError as exc:
        raise exceptions.BusyBarConversionError(
            "Conversion is not supported for this file type",
            path=path,
            original=exc,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("Conversion failed for %s: %s", path, exc)
        raise exceptions.BusyBarConversionError(
            "Failed to convert file for storage",
            path=path,
            original=exc,
        ) from exc
