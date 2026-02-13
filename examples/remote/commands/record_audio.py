from __future__ import annotations

import argparse
import asyncio
import logging
import wave
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from busylib import converter
from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase
from examples.remote.settings import settings

logger = logging.getLogger(__name__)


class InputCapture:
    """
    Coordinate exclusive capture of raw stdin bytes for temporary modes.
    """

    def __init__(self) -> None:
        """
        Initialize capture state.

        Uses a lock to prevent overlapping capture sessions.
        """
        self._handler: Callable[[bytes], bool] | None = None
        self._lock = asyncio.Lock()

    def handle(self, data: bytes) -> bool:
        """
        Dispatch raw input bytes to the active handler, if present.

        Returns True when the data should be consumed by the capture.
        """
        handler = self._handler
        if handler is None:
            return False
        return handler(data)

    @asynccontextmanager
    async def capture(
        self,
        handler: Callable[[bytes], bool],
    ) -> AsyncIterator[None]:
        """
        Activate a handler for exclusive raw input capture.

        The handler is cleared on exit to restore normal input flow.
        """
        async with self._lock:
            self._handler = handler
            try:
                yield
            finally:
                self._handler = None


class AudioRecorder:
    """
    Base class for audio recorders used by remote commands.
    """

    async def start(self) -> None:
        """
        Start capturing audio to the configured target.
        """
        raise NotImplementedError

    async def stop(self) -> None:
        """
        Stop capturing audio and flush recorded data.
        """
        raise NotImplementedError


class SoundDeviceRecorder(AudioRecorder):
    """
    Record audio from the default input device via sounddevice.
    """

    def __init__(
        self,
        target: Path,
        *,
        samplerate: int = 44_100,
        channels: int = 1,
        dtype: str = "int16",
    ) -> None:
        """
        Store recording parameters and output path.
        """
        self._target = target
        self._samplerate = samplerate
        self._channels = channels
        self._dtype = dtype
        self._stream: object | None = None
        self._wave: wave.Wave_write | None = None
        self._errors: list[str] = []

    async def start(self) -> None:
        """
        Start the sounddevice input stream and write frames to disk.
        """
        sounddevice = _load_sounddevice()
        target = self._target
        target.parent.mkdir(parents=True, exist_ok=True)
        wave_file = wave.open(str(target), "wb")
        wave_file.setnchannels(self._channels)
        wave_file.setsampwidth(_dtype_width(self._dtype))
        wave_file.setframerate(self._samplerate)

        def callback(
            indata: bytes,
            _frames: int,
            _time: object,
            status: object,
        ) -> None:
            """
            Write recorded frames to the WAV file.
            """
            if status:
                self._errors.append(str(status))
            wave_file.writeframes(indata)

        stream = sounddevice.RawInputStream(
            samplerate=self._samplerate,
            channels=self._channels,
            dtype=self._dtype,
            callback=callback,
        )
        stream.start()
        self._stream = stream
        self._wave = wave_file

    async def stop(self) -> None:
        """
        Stop recording and close the WAV file.
        """
        stream = self._stream
        wave_file = self._wave
        self._stream = None
        self._wave = None

        if stream is not None:
            stream.stop()
            stream.close()
        if wave_file is not None:
            wave_file.close()
        if self._errors:
            logger.warning("Recording reported issues: %s", "; ".join(self._errors))


class RecordAudioCommand(CommandBase):
    """
    Record audio from the default input and upload it to the device.
    """

    name = "record_audio"
    aliases = ("ra",)

    def __init__(
        self,
        client: AsyncBusyBar,
        status_message: Callable[[str], None],
        input_capture: InputCapture,
        recorder_factory: Callable[[Path], AudioRecorder] | None = None,
    ) -> None:
        """
        Store dependencies for recording and uploading audio.
        """
        self._client = client
        self._status_message = status_message
        self._input_capture = input_capture
        if recorder_factory is None:
            self._recorder_factory = SoundDeviceRecorder
        else:
            self._recorder_factory = recorder_factory

    @classmethod
    def build(cls, **deps: object) -> RecordAudioCommand | None:
        """
        Build the command if required dependencies are available.
        """
        client = deps.get("client")
        status_message = deps.get("status_message")
        input_capture = deps.get("input_capture")
        if (
            isinstance(client, AsyncBusyBar)
            and callable(status_message)
            and isinstance(input_capture, InputCapture)
        ):
            return cls(client, status_message, input_capture)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the record_audio command.
        """
        return CommandArgumentParser(prog="record_audio", add_help=False)

    async def run(self, _args: argparse.Namespace) -> None:
        """
        Record audio, convert it for storage, and upload to the device.
        """
        started_at = datetime.now()
        records_dir = Path("records")
        record_path = build_recording_path(records_dir, started_at)
        stop_event = asyncio.Event()

        def on_input(data: bytes) -> bool:
            """
            Stop the recording on Enter or Esc and consume input.
            """
            if b"\x1b" in data or b"\r" in data or b"\n" in data:
                stop_event.set()
            return True

        logger.info("command:record_audio path=%s", record_path)
        self._status_message("record_audio: recording (Enter/Esc to stop)")
        recorder = self._recorder_factory(record_path)
        try:
            async with self._input_capture.capture(on_input):
                await recorder.start()
                await stop_event.wait()
                await recorder.stop()
            self._status_message(f"record_audio: saved {record_path.name}")
            source_data = record_path.read_bytes()
            self._status_message("record_audio: converting")
            converted_path, converted_data = converter.convert_for_storage(
                str(record_path),
                source_data,
            )
            filename = Path(converted_path).name
            self._status_message(f"record_audio: uploading {filename}")
            await self._client.upload_asset(
                settings.app_id,
                filename,
                converted_data,
            )
            self._status_message("record_audio: done")
        except Exception as exc:  # noqa: BLE001
            logger.exception("command:record_audio failed")
            self._status_message(f"record_audio: error {exc}")


def build_recording_path(records_dir: Path, started_at: datetime) -> Path:
    """
    Build a recording path based on the start timestamp.
    """
    stamp = started_at.strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{stamp}.wav"
    return records_dir / filename


def _dtype_width(dtype: str) -> int:
    """
    Resolve byte width for WAV samples from a dtype name.
    """
    widths = {
        "int16": 2,
        "int24": 3,
        "int32": 4,
        "float32": 4,
    }
    width = widths.get(dtype)
    if width is None:
        raise ValueError(f"Unsupported dtype: {dtype}")
    return width


def _load_sounddevice() -> object:
    """
    Import sounddevice with a clear error message when missing.
    """
    try:
        import sounddevice  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on env
        raise RuntimeError(
            "sounddevice is required for record_audio. Install it first."
        ) from exc
    return sounddevice
