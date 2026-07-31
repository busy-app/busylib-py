from __future__ import annotations

import io
import logging
import re
import wave
import zlib
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from busylib import BusyBar, converter, types

README = Path(__file__).resolve().parents[1] / "README.md"

# Blocks that build their own client, need the network, or are async entry
# points are exercised elsewhere; everything else has to run clean.
SKIP_MARKERS = ("BusyBarDevices", "asyncio.run")


def _responder(request: httpx.Request) -> httpx.Response:
    """
    Answer the endpoints the README touches with realistic payloads.
    """
    path = request.url.path
    bodies: dict[str, Any] = {
        "/api/version": {
            "version": "1.1.1",
            "api_semver": "25.0.0",
            "branch": "release",
        },
        "/api/status": {
            "system": {"uptime": "123"},
            "power": {"battery_charge": 88},
        },
        "/api/display/brightness": {"front": "50", "back": "50"},
        "/api/audio/volume": {"volume": 75},
        "/api/storage/list": {"list": [{"name": "d.txt", "type": "file", "size": 13}]},
    }
    if path in bodies:
        return httpx.Response(200, json=bodies[path])
    if path == "/api/storage/read":
        return httpx.Response(200, content=b"Hello, world!")
    return httpx.Response(200, json={"result": "OK"})


@pytest.fixture
def readme_blocks() -> list[str]:
    """
    Extract the runnable Python blocks from the README.
    """
    blocks = re.findall(r"```python\n(.*?)```", README.read_text(), re.S)
    assert blocks, "no python blocks found in README.md"
    return [b for b in blocks if not any(m in b for m in SKIP_MARKERS)]


@pytest.fixture
def sample_files(tmp_path: Path) -> Path:
    """
    Create the `icon.png` and `alert.wav` the tutorial reads.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (200, 100), "red").save(buffer, format="PNG")
    (tmp_path / "icon.png").write_bytes(buffer.getvalue())

    audio = io.BytesIO()
    with wave.open(audio, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)
    (tmp_path / "alert.wav").write_bytes(audio.getvalue())
    return tmp_path


def test_readme_examples_run_without_warnings(
    readme_blocks: list[str],
    sample_files: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Every runnable README block executes against a mock device, quietly.

    This is what keeps the documented examples honest: an out-of-bounds
    coordinate or a skipped media conversion shows up as a busylib warning,
    which is exactly how the previous examples were broken.
    """
    transport = httpx.MockTransport(_responder)
    original_init = BusyBar.__init__

    def patched_init(self, *args, **kwargs):
        kwargs.setdefault("transport", transport)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(BusyBar, "__init__", patched_init)

    real_open = open

    def scoped_open(path, *args, **kwargs):
        """
        Resolve the tutorial's relative filenames into the temp directory.
        """
        if isinstance(path, str) and not Path(path).is_absolute():
            candidate = sample_files / path
            if candidate.exists():
                path = str(candidate)
        return real_open(path, *args, **kwargs)

    client = BusyBar("10.0.4.20")

    with caplog.at_level(logging.WARNING, logger="busylib"):
        for index, code in enumerate(readme_blocks):
            namespace: dict[str, Any] = {
                "bb": client,
                "BusyBar": BusyBar,
                "types": types,
                "converter": converter,
                "zlib": zlib,
                "open": scoped_open,
                "print": lambda *a, **k: None,
                "__name__": "readme_block",
            }
            try:
                exec(compile(code, f"<readme block {index}>", "exec"), namespace)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"README block {index} raised {type(exc).__name__}: {exc}")

            main = namespace.get("main")
            if callable(main):
                main()

    warnings = [r.getMessage() for r in caplog.records]
    assert not warnings, f"README examples produced busylib warnings: {warnings}"
