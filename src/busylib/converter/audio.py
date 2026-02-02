from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Raw PCM 16-bit little-endian mono at 44.1 kHz as expected by BusyBar firmware.
FFMPEG_ARGS = ["-ar", "44100", "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le"]


def convert(path: str, data: bytes) -> tuple[str, bytes] | None:
    """
    Convert audio bytes into the BusyBar PCM payload.

    Keeps raw PCM as-is and uses ffmpeg for other formats.
    """
    suffix = Path(path).suffix.lower()
    if suffix in {".raw", ".pcm"}:
        return str(Path(path).with_suffix(".wav")), data

    with (
        tempfile.NamedTemporaryFile(suffix=suffix) as src,
        tempfile.NamedTemporaryFile(suffix=".raw") as dst,
    ):
        src.write(data)
        src.flush()
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            src.name,
            *FFMPEG_ARGS,
            dst.name,
        ]
        logger.debug("Running ffmpeg: %s", " ".join(cmd))
        proc = subprocess.run(cmd, check=False, capture_output=True)
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg failed: {stderr.strip()}")
        converted = Path(dst.name).read_bytes()
        new_path = str(Path(path).with_suffix(".wav"))
        return new_path, converted
