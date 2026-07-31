from __future__ import annotations

import argparse
import asyncio
import codecs
import logging
from collections.abc import Callable

from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase
from examples.remote.commands.record_audio import InputCapture
from examples.setup.prompts import SetupAborted
from examples.setup.steps import default_steps
from examples.setup.wizard import collect_status, run_setup

logger = logging.getLogger(__name__)

KEY_ENTER = (10, 13)
KEY_ESCAPE = 27
KEY_BACKSPACE = (8, 127)
KEY_CTRL_C = 3
# Escape introduces a control sequence (arrows send ESC [ A and friends),
# so a bare ESC only counts as "quit" once nothing follows it.
ESC_SEQUENCE_INTRODUCERS = (0x5B, 0x4F)  # '[' and 'O'
# How long to wait for the rest of a sequence before treating ESC as a
# standalone key press.
ESC_SEQUENCE_TIMEOUT_SECONDS = 0.05


class CapturePrompt:
    """
    Prompt implementation for the `remote` TUI.

    Takes exclusive control of raw stdin through `InputCapture` and echoes
    the line being typed into the renderer's transient status line, so the
    wizard is usable without leaving the full-screen view.
    """

    def __init__(
        self,
        input_capture: InputCapture,
        status_message: Callable[[str], None],
        status_line: Callable[[str | None], None],
    ) -> None:
        """
        Store the input capture and the two output surfaces.
        """
        self._input_capture = input_capture
        self._status_message = status_message
        self._status_line = status_line

    def info(self, message: str) -> None:
        """
        Append a line to the remote log.
        """
        self._status_message(message)

    async def text(self, message: str, *, default: str | None = None) -> str:
        """
        Read a visible line of text.
        """
        value = await self._read_line(message, default=default)
        if not value and default is not None:
            return default
        return value

    async def secret(self, message: str) -> str:
        """
        Read a line, echoing it as asterisks.
        """
        return await self._read_line(message, secret=True)

    async def confirm(self, message: str, *, default: bool = True) -> bool:
        """
        Read a yes/no answer, defaulting on empty input.
        """
        hint = "Y/n" if default else "y/N"
        answer = (await self._read_line(f"{message} [{hint}]")).strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes")

    async def choose(self, message: str, options: list[str]) -> int:
        """
        Show a numbered list in the log and read a valid selection.
        """
        if not options:
            raise ValueError("choose() requires at least one option")
        self._status_message(message)
        for index, option in enumerate(options, start=1):
            self._status_message(f"  {index}. {option}")
        while True:
            raw = (await self._read_line(f"Select [1-{len(options)}]")).strip()
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return int(raw) - 1
            self._status_message(f"Enter a number between 1 and {len(options)}.")

    async def _read_line(
        self,
        message: str,
        *,
        secret: bool = False,
        default: str | None = None,
    ) -> str:
        """
        Read one line of raw input, echoing progress to the status line.

        Enter submits. A bare Escape or Ctrl+C leaves the wizard via
        `SetupAborted`; escape sequences such as arrow keys are swallowed
        rather than being mistaken for a quit.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        buffer: list[str] = []
        hint = f" [{default}]" if default else ""
        # Raw stdin delivers UTF-8 one byte at a time, so multi-byte
        # characters have to be reassembled - chr(byte) per byte would
        # mangle any non-ASCII SSID or password typed here.
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        def paint() -> None:
            shown = "*" * len(buffer) if secret else "".join(buffer)
            self._status_line(f"{message}{hint}: {shown}")

        pending_escape = False
        skip_sequence = False
        escape_timer: asyncio.TimerHandle | None = None

        def abort() -> None:
            if not future.done():
                future.set_exception(SetupAborted())

        def cancel_escape_timer() -> None:
            nonlocal escape_timer
            if escape_timer is not None:
                escape_timer.cancel()
                escape_timer = None

        def on_escape_timeout() -> None:
            # Nothing followed the ESC, so it really was a bare key press.
            nonlocal pending_escape
            if pending_escape:
                pending_escape = False
                abort()

        def on_input(data: bytes) -> bool:
            nonlocal pending_escape, skip_sequence, escape_timer
            for byte in data:
                if pending_escape:
                    cancel_escape_timer()
                    # ESC followed by '[' or 'O' is an arrow or function key,
                    # not a quit: swallow the rest of the sequence.
                    pending_escape = False
                    if byte in ESC_SEQUENCE_INTRODUCERS:
                        skip_sequence = True
                        continue
                    abort()
                    return True

                if skip_sequence:
                    # Sequences end on a final byte in the @-~ range.
                    if 0x40 <= byte <= 0x7E:
                        skip_sequence = False
                    continue

                if byte in KEY_ENTER:
                    if not future.done():
                        future.set_result("".join(buffer))
                    return True
                if byte == KEY_ESCAPE:
                    pending_escape = True
                    escape_timer = loop.call_later(
                        ESC_SEQUENCE_TIMEOUT_SECONDS, on_escape_timeout
                    )
                    continue
                if byte == KEY_CTRL_C:
                    abort()
                    return True
                if byte in KEY_BACKSPACE:
                    if buffer:
                        buffer.pop()
                    continue
                if byte >= 32:
                    # Continuation bytes decode to "" until the character
                    # is complete, so nothing lands in the buffer yet.
                    text = decoder.decode(bytes([byte]))
                    if text:
                        buffer.append(text)
            paint()
            return True

        paint()
        try:
            async with self._input_capture.capture(on_input):
                return await future
        finally:
            cancel_escape_timer()
            self._status_line(None)


class SetupCommand(CommandBase):
    """
    Run first-time device setup without leaving the remote view.
    """

    name = "setup"
    aliases = ("wizard",)

    def __init__(
        self,
        client: AsyncBusyBar,
        status_message: Callable[[str], None],
        input_capture: InputCapture,
        status_line: Callable[[str | None], None],
    ) -> None:
        """
        Store the dependencies the wizard and its prompt need.
        """
        self._client = client
        self._status_message = status_message
        self._input_capture = input_capture
        self._status_line = status_line

    @classmethod
    def build(cls, **deps: object) -> SetupCommand | None:
        """
        Build the command when every dependency is available.
        """
        client = deps.get("client")
        status_message = deps.get("status_message")
        input_capture = deps.get("input_capture")
        status_line = deps.get("status_line")
        if (
            isinstance(client, AsyncBusyBar)
            and callable(status_message)
            and isinstance(input_capture, InputCapture)
            and callable(status_line)
        ):
            return cls(client, status_message, input_capture, status_line)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the setup command.
        """
        parser = CommandArgumentParser(prog="setup", add_help=True)
        parser.add_argument(
            "--only",
            choices=[step.key for step in default_steps()],
            default=None,
            help="Run a single step instead of all pending ones",
        )
        parser.add_argument(
            "--redo",
            action="store_true",
            help="Run steps even if the device already satisfies them",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Only show the checklist, changing nothing",
        )
        return parser

    async def run(self, args: argparse.Namespace) -> None:
        """
        Show the checklist and walk through the pending steps.
        """
        logger.info("command:setup only=%s redo=%s", args.only, args.redo)
        prompt = CapturePrompt(
            self._input_capture,
            self._status_message,
            self._status_line,
        )
        try:
            if args.status:
                for report in await collect_status(self._client):
                    prompt.info(report.render())
                return
            await run_setup(
                self._client,
                prompt,
                only=args.only,
                redo=args.redo,
            )
        except SetupAborted:
            self._status_message("setup: cancelled")
        except Exception as exc:  # noqa: BLE001
            logger.exception("command:setup failed")
            self._status_message(f"setup: error {exc}")
