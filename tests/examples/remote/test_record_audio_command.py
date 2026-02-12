from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from examples.remote.commands.record_audio import InputCapture, RecordAudioCommand


class _FakeClient:
    """
    Fake BusyBar client that records upload_asset calls.
    """

    def __init__(self) -> None:
        """
        Initialize call storage.
        """
        self.calls: list[tuple[str, str, bytes]] = []

    async def upload_asset(self, app_id: str, filename: str, data: bytes) -> None:
        """
        Record the upload payload for assertions.
        """
        self.calls.append((app_id, filename, data))


class _FakeRecorder:
    """
    Fake recorder that writes deterministic bytes on stop.
    """

    def __init__(
        self,
        target: Path,
        started: asyncio.Event,
        stopped: asyncio.Event,
    ) -> None:
        """
        Store the target file path and synchronization hooks.
        """
        self._target = target
        self._started = started
        self._stopped = stopped

    async def start(self) -> None:
        """
        Signal that recording has started.
        """
        self._started.set()

    async def stop(self) -> None:
        """
        Write payload bytes and signal stop.
        """
        self._target.parent.mkdir(parents=True, exist_ok=True)
        self._target.write_bytes(b"raw-audio")
        self._stopped.set()


@pytest.mark.asyncio
async def test_record_audio_saves_converts_and_uploads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    Ensure record_audio writes to records dir and uploads converted data.
    """
    fixed_time = datetime(2026, 1, 2, 3, 4, 5, 123456)

    class _FixedDateTime:
        """
        Minimal datetime shim that returns a fixed timestamp.
        """

        @staticmethod
        def now() -> datetime:
            """
            Return the fixed timestamp.
            """
            return fixed_time

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "examples.remote.commands.record_audio.datetime",
        _FixedDateTime,
    )
    monkeypatch.setattr(
        "examples.remote.commands.record_audio.converter.convert_for_storage",
        lambda path, data: ("converted.wav", b"converted"),
    )

    started = asyncio.Event()
    stopped = asyncio.Event()
    input_capture = InputCapture()
    client = _FakeClient()
    status_messages: list[str] = []

    def factory(path: Path) -> _FakeRecorder:
        """
        Build a fake recorder with synchronization hooks.
        """
        return _FakeRecorder(path, started, stopped)

    command = RecordAudioCommand(
        client,
        status_messages.append,
        input_capture,
        recorder_factory=factory,
    )

    task = asyncio.create_task(command.run(argparse.Namespace()))
    await started.wait()
    input_capture.handle(b"\n")
    await asyncio.wait_for(task, timeout=1)

    expected = tmp_path / "records" / "20260102_030405_123456.wav"
    assert expected.exists()
    assert stopped.is_set()
    assert client.calls == [("remote", "converted.wav", b"converted")]
