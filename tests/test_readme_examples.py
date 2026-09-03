from __future__ import annotations

import io
import logging
import shutil
import re
import wave
import zlib
from pathlib import Path
from typing import Any

import httpx2
import pytest
from PIL import Image

from busylib import BusyBar, converter, types, versioning

README = Path(__file__).resolve().parents[1] / "README.md"

# Blocks that build their own client, need the network, or are async entry
# points are exercised elsewhere; everything else has to run clean.
SKIP_MARKERS = ("BusyBarDevices", "asyncio.run")


def test_readme_onboarding_separates_terminal_and_python() -> None:
    """
    Keep the first Windows path explicit about where each command runs.

    This protects against a regression reported by a user who pasted the
    source-only `uv run` command into both a Python file and an interactive
    prompt after the README did not distinguish terminal commands from Python.
    """
    readme = README.read_text(encoding="utf-8")

    assert "Windows (PowerShell)" in readme
    assert "Do not\n  paste terminal commands" in readme
    assert "py -m pip install --upgrade busylib" in readme
    assert "Connected to BUSY Bar. API" in readme
    assert "uv run python -m examples.setup.main" not in readme
    assert "does not run Python examples from this guide" in readme


def test_readme_images_are_absolute() -> None:
    """
    Every image in the README is reachable from off-site.

    PyPI renders this file on its own domain without rewriting relative
    paths, so `assets/...` resolved to a PyPI page - served as HTML with a
    200, which shows up as a broken image rather than a 404. It also strips
    `<source>`, so the `<img>` fallback is the only variant seen there.
    """
    readme = README.read_text(encoding="utf-8")

    references = re.findall(r'(?:src|srcset)="([^"]+)"', readme)

    assert references, "no image references found in README.md"
    relative = [ref for ref in references if not ref.startswith("https://")]
    assert not relative, f"these must be absolute for PyPI: {relative}"


def _responder(request: httpx2.Request) -> httpx2.Response:
    """
    Answer the endpoints the README touches with realistic payloads.
    """
    path = request.url.path
    bodies: dict[str, Any] = {
        # Pinned to the library's own target so a version bump cannot leave
        # the mock device behind and fail every README block at once.
        "/api/version": {
            "version": "1.2.3",
            "api_semver": versioning.API_VERSION,
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
        return httpx2.Response(200, json=bodies[path])
    if path == "/api/storage/read":
        return httpx2.Response(200, content=b"Hello, world!")
    return httpx2.Response(200, json={"result": "OK"})


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


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="the tutorial converts audio, which requires ffmpeg",
)
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
    transport = httpx2.MockTransport(_responder)
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
