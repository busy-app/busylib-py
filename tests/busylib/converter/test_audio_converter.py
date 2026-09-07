from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from busylib.converter import audio


class FakeCompleted:
    """
    Stands in for `subprocess.CompletedProcess`.
    """

    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture
def recorded_ffmpeg(monkeypatch) -> list[list[str]]:
    """
    Capture the argv `convert` would hand to ffmpeg, and fake the output.

    The point of these tests is that the command is correct, so ffmpeg
    itself is never run: requiring the binary made CI install it from apt
    on every job, which failed whenever an unrelated repository on the
    runner image had a stale index.
    """
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs) -> FakeCompleted:
        calls.append(list(cmd))
        # `convert` reads the destination back, so it has to exist.
        Path(cmd[-1]).write_bytes(b"converted-pcm")
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_pcm_payloads_skip_ffmpeg_entirely(monkeypatch) -> None:
    """
    Raw PCM is already what the firmware wants, so nothing is spawned.
    """

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ffmpeg must not run for raw PCM")

    monkeypatch.setattr(subprocess, "run", fail)

    for name in ("beep.raw", "beep.pcm"):
        result = audio.convert(name, b"already-pcm")
        assert result == ("beep.wav", b"already-pcm")


def test_ffmpeg_is_asked_for_the_format_the_firmware_expects(
    recorded_ffmpeg: list[list[str]],
) -> None:
    """
    The command carries the one audio format the bar can play.

    44.1 kHz, mono, signed 16-bit little-endian PCM. A wrong flag here plays
    back as noise on the device, which is not something a mock of `convert`
    would ever catch, so the argv is asserted rather than the effect.
    """
    result = audio.convert("alert.mp3", b"mp3-bytes")

    # `convert` returns None for formats it declines; narrow before unpacking
    # so a regression that stops converting fails here rather than at pyright.
    assert result is not None
    new_path, payload = result

    assert new_path == "alert.wav"
    assert payload == b"converted-pcm"

    assert len(recorded_ffmpeg) == 1
    cmd = recorded_ffmpeg[0]

    assert cmd[0] == "ffmpeg"
    # Never prompt, and keep stderr to actual errors: the output is captured
    # and only read when the exit code is non-zero.
    assert cmd[1:5] == ["-y", "-hide_banner", "-loglevel", "error"]
    assert cmd[5] == "-i"
    assert cmd[6].endswith(".mp3"), "input keeps its suffix so ffmpeg can sniff it"
    assert cmd[7:-1] == [
        "-ar",
        "44100",
        "-ac",
        "1",
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
    ]
    assert cmd[-1].endswith(".raw"), "output is the raw stream, not a container"


def test_ffmpeg_failure_surfaces_its_stderr(monkeypatch) -> None:
    """
    A non-zero exit is reported with what ffmpeg said, not a bare code.
    """

    def fake_run(cmd, **kwargs) -> FakeCompleted:
        return FakeCompleted(returncode=1, stderr=b"  Invalid data found  \n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="ffmpeg failed: Invalid data found"):
        audio.convert("alert.mp3", b"not-really-audio")
