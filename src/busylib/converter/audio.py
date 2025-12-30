from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# PCM 16-bit mono at 8 kHz for BusyBar playback speed compatibility.
FFMPEG_ARGS = ["-ar", "32000", "-ac", "1", "-sample_fmt", "s16"]


def convert(path: str, data: bytes) -> tuple[str, bytes] | None:
    suffix = Path(path).suffix.lower()
    if suffix == ".wav":
        return None

    with tempfile.NamedTemporaryFile(suffix=suffix) as src, tempfile.NamedTemporaryFile(suffix=".wav") as dst:
        src.write(data)
        src.flush()
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src.name, *FFMPEG_ARGS, dst.name]
        logger.debug("Running ffmpeg: %s", " ".join(cmd))
        proc = subprocess.run(cmd, check=False, capture_output=True)
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg failed: {stderr.strip()}")
        converted = Path(dst.name).read_bytes()
        new_path = str(Path(path).with_suffix(".wav"))
        return new_path, converted
