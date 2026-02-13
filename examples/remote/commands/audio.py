from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from busylib import converter, types
from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase
from examples.remote.settings import settings

logger = logging.getLogger(__name__)


def _audio_cache_dir() -> Path:
    """
    Resolve the local cache directory for converted audio assets.

    Uses an explicit setting when provided, otherwise stores files in tmp.
    """
    base_dir = settings.audio_cache_dir
    if base_dir:
        cache_dir = Path(base_dir)
    else:
        cache_dir = Path(tempfile.gettempdir()) / "busylib-remote-audio"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _audio_cache_ttl_seconds() -> float | None:
    """
    Convert cache TTL in days to seconds.

    Returns None when cache cleanup is disabled.
    """
    ttl_days = settings.audio_cache_ttl_days
    if ttl_days is None:
        return None
    if ttl_days <= 0:
        return 0.0
    return float(ttl_days) * 24 * 60 * 60


def _audio_timeout(value: float | None) -> float | None:
    """
    Normalize per-step audio timeout values.

    Non-positive values disable explicit timeout for that step.
    """
    if value is None:
        return None
    if value <= 0:
        return None
    return float(value)


def _audio_cache_key(data: bytes) -> str:
    """
    Build a stable cache key for source audio bytes.

    The digest is used only for local cache indexing.
    """
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def _remote_assets_dir(app_id: str) -> str:
    """
    Build the storage path where app assets are kept on device.
    """
    return f"/ext/assets/{app_id}"


async def _list_remote_assets(
    client: AsyncBusyBar,
    app_id: str,
) -> set[str]:
    """
    Return a set of asset names currently present on the device.

    Errors are treated as an empty listing to keep audio flow resilient.
    """
    remote_dir = _remote_assets_dir(app_id)
    try:
        listing = await client.list_storage_files(remote_dir)
    except Exception as exc:  # noqa: BLE001
        logger.debug("audio: failed to list remote assets: %s", exc)
        return set()

    names: set[str] = set()
    for entry in listing.list:
        if isinstance(entry, types.StorageFileElement):
            names.add(entry.name)
    return names


def _load_cached_audio(
    cache_dir: Path,
    cache_key: str,
) -> tuple[str, bytes] | None:
    """
    Load cached converted audio for a known cache key.

    Returns filename and bytes when cache entries are present and valid.
    """
    meta_path = cache_dir / f"{cache_key}.json"
    data_path = cache_dir / f"{cache_key}.bin"
    if not meta_path.exists() or not data_path.exists():
        return None
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        filename = str(metadata.get("filename", ""))
        if not filename:
            return None
        return filename, data_path.read_bytes()
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _touch_cached_audio(meta_path: Path, filename: str) -> None:
    """
    Update metadata for a cached asset use.

    Stores the latest access timestamp used by cache cleanup.
    """
    payload = {
        "filename": filename,
        "last_used": time.time(),
    }
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=True),
        encoding="utf-8",
    )


def _store_cached_audio(
    cache_dir: Path,
    cache_key: str,
    filename: str,
    data: bytes,
) -> None:
    """
    Persist converted audio payload and metadata in cache.

    Cache consists of a JSON metadata file and binary payload file.
    """
    meta_path = cache_dir / f"{cache_key}.json"
    data_path = cache_dir / f"{cache_key}.bin"
    _touch_cached_audio(meta_path, filename)
    data_path.write_bytes(data)


def _cleanup_audio_cache(cache_dir: Path) -> None:
    """
    Remove stale cached assets according to configured TTL.

    Invalid metadata files are treated as stale and removed.
    """
    ttl_seconds = _audio_cache_ttl_seconds()
    if ttl_seconds is None:
        return

    now = time.time()
    for meta_path in cache_dir.glob("*.json"):
        data_path = cache_dir / f"{meta_path.stem}.bin"
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            last_used = float(metadata.get("last_used", meta_path.stat().st_mtime))
        except (OSError, ValueError, json.JSONDecodeError):
            last_used = meta_path.stat().st_mtime if meta_path.exists() else now

        if ttl_seconds == 0.0 or now - last_used > ttl_seconds:
            meta_path.unlink(missing_ok=True)
            data_path.unlink(missing_ok=True)

    for data_path in cache_dir.glob("*.bin"):
        meta_path = cache_dir / f"{data_path.stem}.json"
        if not meta_path.exists():
            data_path.unlink(missing_ok=True)


class AudioCommand(CommandBase):
    """
    Upload and play an audio file on the device.
    """

    name = "audio"
    aliases = ("a",)

    def __init__(
        self,
        client: AsyncBusyBar,
        status_message: Callable[[str], None],
    ) -> None:
        """
        Store the client used to upload and play audio.
        """
        self._client = client
        self._status_message = status_message

    @classmethod
    def build(cls, **deps: object) -> AudioCommand | None:
        """
        Build the command if the client and status callback are available.
        """
        client = deps.get("client")
        status_message = deps.get("status_message")
        if isinstance(client, AsyncBusyBar) and callable(status_message):
            return cls(client, status_message)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the audio command.
        """
        parser = CommandArgumentParser(prog="audio", add_help=True)
        parser.add_argument("path", help="Path to the audio file")
        return parser

    async def run(self, args: argparse.Namespace) -> None:
        """
        Convert, upload, and play the provided audio file.

        Converted files are cached locally and reused for repeated inputs.
        """
        source_path = Path(args.path)
        logger.info("command:audio path=%s", source_path)
        self._status_message(f"audio: reading {source_path.name}")
        try:
            data = source_path.read_bytes()
            cache_dir = _audio_cache_dir()
            cache_key = _audio_cache_key(data)
            _cleanup_audio_cache(cache_dir)
            cached = _load_cached_audio(cache_dir, cache_key)

            if cached:
                filename, converted_data = cached
                _touch_cached_audio(cache_dir / f"{cache_key}.json", filename)
                self._status_message("audio: using cached conversion")
            else:
                self._status_message("audio: converting")
                converted_path, converted_data = converter.convert_for_storage(
                    str(source_path),
                    data,
                )
                filename = Path(converted_path).name
                _store_cached_audio(cache_dir, cache_key, filename, converted_data)

            self._status_message("audio: checking remote assets")
            remote_assets = await _list_remote_assets(self._client, settings.app_id)
            self._status_message(f"audio: remote has {len(remote_assets)} assets")
            if filename in remote_assets:
                self._status_message(f"audio: refreshing {filename}")
            else:
                self._status_message(f"audio: uploading {filename}")

            upload_timeout = _audio_timeout(settings.audio_upload_timeout_seconds)
            if upload_timeout is None:
                await self._client.upload_asset(
                    settings.app_id,
                    filename,
                    converted_data,
                )
            else:
                await asyncio.wait_for(
                    self._client.upload_asset(
                        settings.app_id,
                        filename,
                        converted_data,
                    ),
                    timeout=upload_timeout,
                )
            self._status_message(f"audio: playing {filename}")

            play_timeout = _audio_timeout(settings.audio_play_timeout_seconds)
            if play_timeout is None:
                await self._client.play_audio(settings.app_id, filename)
            else:
                await asyncio.wait_for(
                    self._client.play_audio(settings.app_id, filename),
                    timeout=play_timeout,
                )
            self._status_message("audio: done")
        except asyncio.TimeoutError:
            logger.exception("command:audio timeout")
            self._status_message("audio: error timeout")
        except Exception as exc:  # noqa: BLE001
            logger.exception("command:audio failed")
            self._status_message(f"audio: error {exc}")


class AudioStopCommand(CommandBase):
    """
    Stop currently playing audio on the device.
    """

    name = "audio_stop"
    aliases = ("as", "astop")

    def __init__(
        self,
        client: AsyncBusyBar,
        status_message: Callable[[str], None],
    ) -> None:
        """
        Store the client used to stop active audio playback.
        """
        self._client = client
        self._status_message = status_message

    @classmethod
    def build(cls, **deps: object) -> AudioStopCommand | None:
        """
        Build the command if required dependencies are available.
        """
        client = deps.get("client")
        status_message = deps.get("status_message")
        if isinstance(client, AsyncBusyBar) and callable(status_message):
            return cls(client, status_message)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the audio_stop command.
        """
        return CommandArgumentParser(prog="audio_stop", add_help=False)

    async def run(self, _args: argparse.Namespace) -> None:
        """
        Stop audio playback and emit status for command mode.
        """
        logger.info("command:audio_stop")
        try:
            await self._client.stop_audio()
            self._status_message("audio: stopped")
        except Exception as exc:  # noqa: BLE001
            logger.exception("command:audio_stop failed")
            self._status_message(f"audio: error {exc}")
