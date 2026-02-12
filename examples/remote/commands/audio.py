from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from pathlib import Path

from busylib import converter
from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase
from examples.remote.settings import settings

logger = logging.getLogger(__name__)


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
        """
        source_path = Path(args.path)
        logger.info("command:audio path=%s", source_path)
        self._status_message(f"audio: reading {source_path.name}")
        try:
            data = source_path.read_bytes()
            self._status_message("audio: converting")
            converted_path, converted_data = converter.convert_for_storage(
                str(source_path),
                data,
            )
            filename = Path(converted_path).name
            self._status_message(f"audio: uploading {filename}")
            await self._client.upload_asset(
                settings.app_id,
                filename,
                converted_data,
            )
            self._status_message(f"audio: playing {filename}")
            await self._client.play_audio(settings.app_id, filename)
            self._status_message("audio: done")
        except Exception as exc:  # noqa: BLE001
            logger.exception("command:audio failed")
            self._status_message(f"audio: error {exc}")
