from __future__ import annotations

import asyncio
import json
import os
import sys
import termios
import tty
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .types import InputKey

TermiosAttrs = (
    list[int | list[bytes | int]] | list[int | list[bytes]] | list[int | list[int]]
)


def _termios_flags(attrs: TermiosAttrs) -> int:
    """
    Extract termios flag field as an integer.
    """
    flags = attrs[0]
    if not isinstance(flags, int):
        raise TypeError("termios flags must be int")
    return flags


@dataclass(frozen=True)
class KeyMap:
    mapping: dict[bytes, InputKey]
    labels: dict[bytes, str]
    help_sequences: set[bytes]
    exit_sequences: set[bytes]
    reader_factory: Callable[..., object] | None = None
    decoder_factory: Callable[..., object] | None = None


def _encode_human_key(spec: str) -> bytes:
    """
    Convert human-friendly key spec to the underlying byte sequence.

    Supported forms:
    - plain characters (e.g., "k", ",", " ")
    - control keys: "ctrl+x" (single character after '+')
    - special names: "up", "down", "left", "right", "enter", "return", "esc", "space"
    - escape sequences may still be passed directly (e.g., "\\x1b[A")
    """
    lower = spec.lower()
    specials = {
        "up": "\x1b[A",
        "down": "\x1b[B",
        "left": "\x1b[D",
        "right": "\x1b[C",
        "enter": "\r",
        "return": "\r",
        "esc": "\x1b",
        "space": " ",
        "comma": ",",
    }
    if lower in specials:
        return specials[lower].encode("utf-8")

    if lower.startswith("ctrl+") and len(lower) == 6:
        ch = lower[-1]
        code = ord(ch) & 0x1F
        return bytes((code,))

    try:
        return spec.encode("utf-8").decode("unicode_escape").encode("utf-8")
    except UnicodeDecodeError:
        return spec.encode("utf-8")


_DEFAULT_KEYMAP_HUMAN: dict[str, InputKey] = {
    "up": InputKey.UP,
    "down": InputKey.DOWN,
    "right": InputKey.OK,
    "enter": InputKey.OK,
    "return": InputKey.OK,
    "left": InputKey.BACK,
    "esc": InputKey.BACK,
    "space": InputKey.START,
    "ctrl+b": InputKey.BUSY,
    "ctrl+s": InputKey.STATUS,
    "ctrl+o": InputKey.OFF,
    "ctrl+a": InputKey.APPS,
    "ctrl+p": InputKey.SETTINGS,
}

_DEFAULT_HELP_KEYS: set[str] = set()
_DEFAULT_EXIT_KEYS = {"ctrl+q"}


def _build_keymap(
    human_map: dict[str, InputKey], help_keys: set[str], exit_keys: set[str]
) -> KeyMap:
    mapping: dict[bytes, InputKey] = {}
    labels: dict[bytes, str] = {}

    def add(seq: bytes, label: str, key: InputKey) -> None:
        mapping[seq] = key
        labels[seq] = label

    for human, key in human_map.items():
        seq = _encode_human_key(human)
        add(seq, human, key)

        # Provide terminal sequence variants for arrows and enter.
        if human in {"up", "down", "left", "right"}:
            if seq.startswith(b"\x1b[") and len(seq) == 3:
                ss3_variant = b"\x1bO" + seq[-1:]
                add(ss3_variant, f"{human}-ss3", key)
        if human in {"enter", "return"}:
            add(b"\n", "newline", key)
        if human == "esc":
            add(b"\x1b", "esc", key)

    help_sequences = {_encode_human_key(k) for k in help_keys}
    exit_sequences = {_encode_human_key(k) for k in exit_keys}
    return KeyMap(
        mapping=mapping,
        labels=labels,
        help_sequences=help_sequences,
        exit_sequences=exit_sequences,
    )


def default_keymap() -> KeyMap:
    """
    Return default keymap with human-readable labels and meta keys.
    """
    return _build_keymap(
        _DEFAULT_KEYMAP_HUMAN, set(_DEFAULT_HELP_KEYS), set(_DEFAULT_EXIT_KEYS)
    )


def load_keymap(path: str | Path | None) -> KeyMap:
    """
    Load a keymap from JSON file if provided, otherwise return the default.

    JSON format: {"<human_key>": "<input_key_name>"} where key names match
    InputKey values (e.g., "up", "down", "ok") and keys can be human-friendly
    like "ctrl+k", "enter", "esc", or plain characters.
    """
    if not path:
        return default_keymap()

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    human_map: dict[str, InputKey] = {}
    for seq, key_name in data.items():
        try:
            key = InputKey(key_name)
        except ValueError as exc:
            raise ValueError(f"Unknown input key in keymap: {key_name}") from exc
        human_map[seq] = key
    return _build_keymap(human_map, set(_DEFAULT_HELP_KEYS), set(_DEFAULT_EXIT_KEYS))


class StdinReader:
    """
    Raw stdin reader that collects key sequences.
    """

    def __init__(
        self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[bytes]
    ) -> None:
        self.loop = loop
        self.queue = queue
        self.fd = sys.stdin.fileno()
        self._old_settings: TermiosAttrs | None = None

    def start(self) -> None:
        self._old_settings = cast(TermiosAttrs, termios.tcgetattr(self.fd))
        new_settings = cast(TermiosAttrs, termios.tcgetattr(self.fd))
        flags = _termios_flags(new_settings)
        new_settings[0] = flags & ~(termios.IXON | termios.IXOFF | termios.IXANY)
        termios.tcsetattr(self.fd, termios.TCSANOW, new_settings)
        tty.setcbreak(self.fd)
        self.loop.add_reader(self.fd, self._on_input)

    def _on_input(self) -> None:
        try:
            data = os.read(self.fd, 32)
        except OSError:
            return
        if data:
            self.queue.put_nowait(data)

    def stop(self) -> None:
        self.loop.remove_reader(self.fd)
        if self._old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_settings)


class KeyDecoder:
    """
    Decode raw byte sequences to InputKey with support for exit/help.
    """

    def __init__(self, keymap: KeyMap) -> None:
        self.mapping = keymap.mapping
        self.exit_sequences = keymap.exit_sequences
        self._buffer = b""
        all_sequences = set(self.mapping) | self.exit_sequences
        self._sequences = sorted(all_sequences, key=lambda s: (-len(s), s))
        self._prefixes = {seq[:i] for seq in all_sequences for i in range(1, len(seq))}

    def feed(self, chunk: bytes) -> list[tuple[bytes, InputKey | None]]:
        events: list[tuple[bytes, InputKey | None]] = []
        self._buffer += chunk
        while self._buffer:
            match = next(
                (seq for seq in self._sequences if self._buffer.startswith(seq)), None
            )
            if match:
                events.append((match, self.mapping.get(match)))
                self._buffer = self._buffer[len(match) :]
                continue
            if any(prefix.startswith(self._buffer) for prefix in self._prefixes):
                break
            first = self._buffer[:1]
            if first in self.mapping or first in self.exit_sequences:
                events.append((first, self.mapping.get(first)))
            self._buffer = self._buffer[1:]
        return events
