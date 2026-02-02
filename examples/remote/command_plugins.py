from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from busylib import converter, display, types

from busylib.client import AsyncBusyBar

from .commands import CommandArgumentParser, CommandBase
from .settings import settings

logger = logging.getLogger(__name__)

DANGEROUS_PREFIXES = (
    "set_",
    "delete_",
    "update_",
    "upload_",
    "write_",
    "install_",
    "abort_",
    "unlink_",
    "reboot",
    "reset",
    "usb_",
    "format_",
    "clear_",
)
BLACKLISTED_METHODS = {
    "aclose",
}


def _format_call_result(result: object) -> str:
    """
    Format a call result for status output.
    """
    if result is None:
        return "ok"
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    if isinstance(result, bytes):
        return f"bytes:{len(result)}"
    if isinstance(result, (dict, list, str, int, float, bool)):
        return json.dumps(result, ensure_ascii=True, separators=(",", ":"))
    return repr(result)


class TextCommand(CommandBase):
    """
    Draw a large scrolling text on the front display.
    """

    name = "text"
    aliases = ("t",)

    def __init__(self, client: AsyncBusyBar) -> None:
        """
        Store the client used to send drawing commands.
        """
        self._client = client

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the text command.
        """
        parser = CommandArgumentParser(prog="text", add_help=True)
        parser.add_argument("text", nargs="+", help="Text to render")
        parser.add_argument(
            "--x",
            type=int,
            default=0,
            help="X-position",
        )
        parser.add_argument(
            "--y",
            type=int,
            default=8,
            help="Y-position",
        )
        parser.add_argument(
            "--font",
            choices=["small", "medium", "medium_condensed", "big"],
            default="big",
            help="Font name",
        )
        parser.add_argument(
            "--align",
            choices=[
                "top_left",
                "top_mid",
                "top_right",
                "mid_left",
                "center",
                "mid_right",
                "bottom_left",
                "bottom_mid",
                "bottom_right",
            ],
            default="mid_left",
            help="Text alignment",
        )
        parser.add_argument(
            "--scroll-rate",
            type=int,
            default=1000,
            help="Scroll rate for long text",
        )
        return parser

    async def run(self, args: argparse.Namespace) -> None:
        """
        Send the text element to the display.
        """
        logger.info("command:text")
        message = " ".join(args.text).strip()
        if not message:
            return
        spec = display.get_display_spec(display.FRONT_DISPLAY)
        scroll_rate = (
            args.scroll_rate if args.scroll_rate and args.scroll_rate > 0 else None
        )
        element = types.TextElement(
            id="remote_cmd_text",
            x=args.x,
            y=args.y,
            text=message,
            font=args.font,
            align=args.align,
            width=spec.width,
            scroll_rate=scroll_rate,
            display=types.DisplayName.FRONT,
        )
        payload = types.DisplayElements(app_id="remote_command", elements=[element])
        await self._client.draw_on_display(payload)


class QuitCommand(CommandBase):
    """
    Stop the remote loop.
    """

    name = "quit"
    aliases = ("q", "exit")

    def __init__(self, stop_event: asyncio.Event) -> None:
        """
        Store the stop event to signal shutdown.
        """
        self._stop_event = stop_event

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for quit.
        """
        return CommandArgumentParser(prog="q", add_help=False)

    async def run(self, _args: argparse.Namespace) -> None:
        """
        Signal the remote loop to stop.
        """
        logger.info("command:quit")
        self._stop_event.set()


class ClearCommand(CommandBase):
    """
    Clear the remote display on demand.
    """

    name = "clear"
    aliases = ("c",)

    def __init__(self, client: AsyncBusyBar) -> None:
        """
        Store the client used to clear the display.
        """
        self._client = client

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the clear command.
        """
        return CommandArgumentParser(prog="clear", add_help=False)

    async def run(self, args: argparse.Namespace) -> None:
        """
        Clear the remote display.
        """
        logger.info("command:clear")
        await self._client.clear_display()


class ClockCommand(CommandBase):
    """
    Open the clock app via input key sequence.
    """

    name = "clock"

    def __init__(self, client: AsyncBusyBar) -> None:
        """
        Store the client used to send input keys.
        """
        self._client = client

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the clock command.
        """
        return CommandArgumentParser(prog="clock", add_help=False)

    async def run(self, _args: argparse.Namespace) -> None:
        """
        Trigger the clock app sequence.
        """
        logger.info("command:clock")
        await self._client.send_input_key(types.InputKey.APPS)
        await asyncio.sleep(0.2)
        await self._client.send_input_key(types.InputKey.OK)
        await asyncio.sleep(0.2)
        await self._client.send_input_key(types.InputKey.OK)


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


def build_call_handler(
    client: AsyncBusyBar,
    status_message: Callable[[str], None],
) -> Callable[[list[str]], Awaitable[None]]:
    """
    Build a handler that calls BusyBar client methods from command arguments.
    """

    async def _handler(args: list[str]) -> None:
        """
        Dispatch a method call with key=value arguments.
        """
        if not args:
            logger.warning("call: missing method name")
            status_message("call: missing method name")
            return

        method_name = args[0].strip()
        if not method_name:
            logger.warning("call: empty method name")
            status_message("call: empty method name")
            return
        if method_name.startswith("_") or method_name in BLACKLISTED_METHODS:
            logger.warning("call: method %s is not allowed", method_name)
            status_message(f"call {method_name}: not allowed")
            return

        method = getattr(client, method_name, None)
        if method is None or not callable(method):
            logger.warning("call: method %s not found", method_name)
            status_message(f"call {method_name}: not found")
            return

        force = False
        kwargs: dict[str, str] = {}
        for token in args[1:]:
            if token == "--force" or token.startswith("--force="):
                force = True
                continue
            if "=" not in token:
                logger.warning("call: argument %s must be key=value", token)
                status_message(f"call {method_name}: invalid arg {token}")
                return
            key, value = token.split("=", 1)
            if not key:
                logger.warning("call: empty argument name in %s", token)
                status_message(f"call {method_name}: empty arg name")
                return
            kwargs[key] = value

        if method_name.startswith(DANGEROUS_PREFIXES) and not force:
            logger.warning("call: method %s requires --force", method_name)
            status_message(f"call {method_name}: requires --force")
            return

        logger.info("command:call %s %s", method_name, kwargs)
        try:
            result = method(**kwargs)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:  # noqa: BLE001
            logger.exception("call: failed %s", method_name)
            status_message(f"call {method_name}: error {exc}")
            return
        status_message(f"call {method_name}: {_format_call_result(result)}")

    return _handler
