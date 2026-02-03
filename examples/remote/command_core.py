from __future__ import annotations

import argparse
import asyncio
import codecs
import shlex
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeAlias

CommandHandler = Callable[[list[str]], Awaitable[None] | None]
CommandEvent = tuple[str, tuple[str, int] | str | None]
CommandResult = tuple[bool, str | None]


class CommandInput:
    """
    Command-line input handler with history and escape sequence parsing.
    """

    def __init__(
        self, history_path: Path | None = None, max_history: int = 100
    ) -> None:
        """
        Initialize command input state.

        Stores the current buffer, history list, and escape parsing buffer.
        """
        self._buffer = ""
        self._cursor = 0
        self._history: list[str] = []
        self._history_index: int | None = None
        self._seq_buffer = b""
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._arrow_sequences = {
            b"\x1b[A": "up",
            b"\x1bOA": "up",
            b"\x1b[B": "down",
            b"\x1bOB": "down",
            b"\x1b[C": "right",
            b"\x1bOC": "right",
            b"\x1b[D": "left",
            b"\x1bOD": "left",
        }
        self._history_path = history_path or Path("remote_history.log")
        self._max_history = max_history
        self._load_history()

    def begin(self) -> None:
        """
        Reset the input buffer for a new command line.

        History is preserved between command entries.
        """
        self._buffer = ""
        self._cursor = 0
        self._history_index = None
        self._seq_buffer = b""
        self._decoder.reset()

    @property
    def buffer(self) -> str:
        """
        Return the current input buffer.
        """
        return self._buffer

    @property
    def cursor(self) -> int:
        """
        Return the current cursor position within the buffer.
        """
        return self._cursor

    def feed(self, data: bytes) -> list[CommandEvent]:
        """
        Consume raw input bytes and return command input events.

        Events: ("update", (buffer, cursor)), ("submit", line), ("cancel", None).
        """
        events: list[CommandEvent] = []
        for idx, byte in enumerate(data):
            if self._seq_buffer:
                self._seq_buffer += bytes([byte])
                if self._seq_buffer in self._arrow_sequences:
                    direction = self._arrow_sequences[self._seq_buffer]
                    self._seq_buffer = b""
                    self._apply_history(direction, events)
                    continue
                if any(
                    seq.startswith(self._seq_buffer) for seq in self._arrow_sequences
                ):
                    continue
                self._seq_buffer = b""

            if byte == 27:  # ESC or start of arrow
                if idx == len(data) - 1:
                    events.append(("cancel", None))
                    continue
                self._seq_buffer = b"\x1b"
                continue

            if byte in (10, 13):  # Enter
                line = self._buffer.strip()
                if line:
                    self._history.append(line)
                    self._append_history(line)
                self._buffer = ""
                self._cursor = 0
                self._history_index = None
                self._seq_buffer = b""
                self._decoder.reset()
                events.append(("submit", line))
                continue

            if byte in (8, 127):  # Backspace
                if self._cursor > 0:
                    self._buffer = (
                        self._buffer[: self._cursor - 1] + self._buffer[self._cursor :]
                    )
                    self._cursor -= 1
                    events.append(("update", (self._buffer, self._cursor)))
                continue

            if byte >= 32 and byte != 127:
                text = self._decoder.decode(bytes([byte]))
                if text:
                    for char in text:
                        self._buffer = (
                            self._buffer[: self._cursor]
                            + char
                            + self._buffer[self._cursor :]
                        )
                        self._cursor += 1
                    events.append(("update", (self._buffer, self._cursor)))

        return events

    def _load_history(self) -> None:
        """
        Load history entries from the configured history file.

        Missing or unreadable files are ignored.
        """
        path = self._history_path
        try:
            if not path.exists():
                return
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        self._history = [line for line in lines if line.strip()][-self._max_history :]

    def _append_history(self, line: str) -> None:
        """
        Append a new history entry to the history file.
        """
        path = self._history_path
        try:
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(self._history) + "\n", encoding="utf-8")
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            return

    def _apply_history(self, direction: str, events: list[CommandEvent]) -> None:
        """
        Update the buffer based on history navigation.

        Direction is "up" or "down".
        """
        if direction == "left":
            if self._cursor > 0:
                self._cursor -= 1
                events.append(("update", (self._buffer, self._cursor)))
            return

        if direction == "right":
            if self._cursor < len(self._buffer):
                self._cursor += 1
                events.append(("update", (self._buffer, self._cursor)))
            return

        if not self._history:
            return
        if direction == "up":
            if self._history_index is None:
                self._history_index = len(self._history) - 1
            else:
                self._history_index = max(0, self._history_index - 1)
            self._buffer = self._history[self._history_index]
            self._cursor = len(self._buffer)
            events.append(("update", (self._buffer, self._cursor)))
            return

        if direction == "down":
            if self._history_index is None:
                return
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self._buffer = self._history[self._history_index]
            else:
                self._history_index = None
                self._buffer = ""
            self._cursor = len(self._buffer)
            events.append(("update", (self._buffer, self._cursor)))
            return


def register(command: str, handler: CommandHandler) -> None:
    """
    Register a command handler in the default registry.

    This provides a simple module-level API for extensions.
    """
    _DEFAULT_REGISTRY.register(command, handler)


def register_command(
    registry: CommandRegistry,
    command: str | CommandBase,
    handler: CommandHandler | None = None,
) -> None:
    """
    Register a command handler or command object in the provided registry.
    """
    if isinstance(command, CommandBase):
        registry.register_command(command)
        for alias in command.aliases:
            registry.register(alias, command.handle)
        return
    if handler is None:
        raise ValueError("Handler must be provided for string command names")
    registry.register(command, handler)


class CommandParseError(ValueError):
    """
    Raised when a command fails to parse its arguments.
    """


class CommandArgumentParser(argparse.ArgumentParser):
    """
    Argument parser that raises instead of exiting.
    """

    def error(self, message: str) -> None:  # noqa: D401 - argparse signature
        """
        Raise a parse error instead of writing to stderr.
        """
        raise CommandParseError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        """
        Raise a parse error instead of exiting the process.
        """
        raise CommandParseError(message or "Command parsing failed")


class CommandBase:
    """
    Base class for argparse-powered commands.
    """

    name: str
    aliases: list[str] = []

    def build_parser(self) -> CommandArgumentParser:
        """
        Build and return an argument parser for the command.
        """
        raise NotImplementedError

    async def run(self, args: argparse.Namespace) -> None:
        """
        Execute the command using parsed arguments.
        """
        raise NotImplementedError

    async def handle(self, argv: list[str]) -> CommandResult:
        """
        Parse arguments and run the command.

        Returns a tuple of (handled, error_message).
        """
        parser = self.build_parser()
        try:
            parsed = parser.parse_args(self._normalize_argv(argv))
        except CommandParseError as exc:
            message = str(exc) if str(exc) else "Invalid command arguments"
            return False, message
        await self.run(parsed)
        return True, None

    @classmethod
    def build(cls, **_deps: object) -> CommandBase | None:
        """
        Optionally build the command with provided dependencies.

        Returns None when the command cannot be constructed.
        """
        return None

    def _normalize_argv(self, argv: list[str]) -> list[str]:
        """
        Normalize argv to support key=value and dash aliases.

        Converts tokens like "x=1" to "--x 1" and "scroll-rate=10" to
        "--scroll-rate 10" so argparse can handle them.
        """
        normalized: list[str] = []
        for token in argv:
            if "=" in token and not token.startswith("-"):
                key, value = token.split("=", 1)
                if not key:
                    normalized.append(token)
                    continue
                normalized.extend([f"--{key}", value])
                continue
            normalized.append(token)
        return normalized


CommandEntry: TypeAlias = CommandHandler | CommandBase


class CommandRegistry:
    """
    Registry for command handlers used by the remote command mode.
    """

    def __init__(self) -> None:
        """
        Initialize an empty command registry.

        Handlers are stored under normalized lowercase command names.
        """
        self._handlers: dict[str, CommandEntry] = {}

    def register(self, command: str, handler: CommandHandler) -> None:
        """
        Register a command handler by name.

        The command name is normalized to lowercase and stripped of whitespace.
        """
        name = command.strip().lower()
        if not name:
            raise ValueError("Command name must be non-empty")
        self._handlers[name] = handler

    def register_command(self, command: CommandEntry) -> None:
        """
        Register a command entry that knows its own name.
        """
        if isinstance(command, CommandBase):
            self._handlers[command.name] = command
            return
        raise TypeError("Command entry must be a CommandBase")

    async def handle(self, line: str) -> CommandResult:
        """
        Parse a command line and dispatch to the registered handler.

        Returns a tuple of (handled, error_message).
        """
        parts = self._split_line(line)
        if not parts:
            return False, None
        name = parts[0].lower()
        handler = self._handlers.get(name)
        if handler is None:
            return False, f"Unknown command: {name}"
        if isinstance(handler, CommandBase):
            return await handler.handle(parts[1:])
        result = handler(parts[1:])
        if asyncio.iscoroutine(result):
            await result
        return True, None

    @staticmethod
    def _split_line(line: str) -> list[str]:
        """
        Split the command line respecting quotes.
        """
        try:
            return shlex.split(line, posix=True)
        except ValueError:
            return []


_DEFAULT_REGISTRY = CommandRegistry()


def get_registry() -> CommandRegistry:
    """
    Return the default command registry.

    Consumers can use it to register or invoke commands.
    """
    return _DEFAULT_REGISTRY
