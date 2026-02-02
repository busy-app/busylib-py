from __future__ import annotations

import asyncio
import json
import os
import sys
import termios
import tty
from collections.abc import Callable
from pathlib import Path
from typing import cast

from busylib.types import InputKey

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


class KeyMap:
    """
    Keymap definition with decoded inputs and helper metadata.
    """

    def __init__(
        self,
        mapping: dict[bytes, InputKey],
        labels: dict[bytes, str],
        help_sequences: set[bytes],
        exit_sequences: set[bytes],
        reader_factory: Callable[..., object] | None = None,
        decoder_factory: Callable[..., object] | None = None,
    ) -> None:
        """
        Initialize keymap storage with mappings and helper metadata.

        Stores raw byte mappings, UI labels, and auxiliary factories.
        """
        self.mapping = mapping
        self.labels = labels
        self.help_sequences = help_sequences
        self.exit_sequences = exit_sequences
        self.reader_factory = reader_factory
        self.decoder_factory = decoder_factory


def _encode_human_key(spec: str) -> bytes:
    """
    Convert human-friendly key spec to the underlying byte sequence.

    Supported forms:
    - plain characters (e.g., "k", ",", " ")
    - control keys: "ctrl+x" (single character after '+')
    - function keys: "f1" .. "f5"
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
        "f1": "\x1bOP",
        "f2": "\x1bOQ",
        "f3": "\x1bOR",
        "f4": "\x1bOS",
        "f5": "\x1b[15~",
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
    "f1": InputKey.BUSY,
    "f2": InputKey.STATUS,
    "f3": InputKey.OFF,
    "f4": InputKey.APPS,
    "f5": InputKey.SETTINGS,
}

_DEFAULT_HELP_KEYS: set[str] = set()
_DEFAULT_EXIT_KEYS = {"ctrl+q"}


def _build_keymap(
    human_map: dict[str, InputKey], help_keys: set[str], exit_keys: set[str]
) -> KeyMap:
    """
    Build a KeyMap from human-friendly key specs and metadata.

    Adds terminal variants for arrows and enter sequences.
    """
    mapping: dict[bytes, InputKey] = {}
    labels: dict[bytes, str] = {}

    def add(seq: bytes, label: str, key: InputKey) -> None:
        mapping[seq] = key
        labels[seq] = label

    for human, key in human_map.items():
        seq = _encode_human_key(human)
        add(seq, human, key)

        # Provide terminal sequence variants for arrows, enter, and function keys.
        if human in {"up", "down", "left", "right"}:
            if seq.startswith(b"\x1b[") and len(seq) == 3:
                ss3_variant = b"\x1bO" + seq[-1:]
                add(ss3_variant, f"{human}-ss3", key)
        if human in {"enter", "return"}:
            add(b"\n", "newline", key)
        if human == "esc":
            add(b"\x1b", "esc", key)
        if human in {"f1", "f2", "f3", "f4", "f5"}:
            fkey_variants = {
                "f1": (b"\x1b[11~",),
                "f2": (b"\x1b[12~",),
                "f3": (b"\x1b[13~",),
                "f4": (b"\x1b[14~",),
                "f5": (b"\x1b[15~",),
            }
            for variant in fkey_variants[human]:
                add(variant, f"{human}-alt", key)

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
        """
        Initialize stdin reader with event loop and output queue.

        Stores file descriptor state for raw input mode.
        """
        self.loop = loop
        self.queue = queue
        self.fd = sys.stdin.fileno()
        self._old_settings: TermiosAttrs | None = None

    def start(self) -> None:
        """
        Enable raw input mode and register the loop reader callback.

        Configures termios flags and cbreak mode.
        """
        self._old_settings = cast(TermiosAttrs, termios.tcgetattr(self.fd))
        new_settings = cast(TermiosAttrs, termios.tcgetattr(self.fd))
        flags = _termios_flags(new_settings)
        new_settings[0] = flags & ~(termios.IXON | termios.IXOFF | termios.IXANY)
        termios.tcsetattr(self.fd, termios.TCSANOW, new_settings)
        tty.setcbreak(self.fd)
        self.loop.add_reader(self.fd, self._on_input)

    def _on_input(self) -> None:
        """
        Read raw bytes from stdin and enqueue them.

        Ignores transient OS errors.
        """
        try:
            data = os.read(self.fd, 32)
        except OSError:
            return
        if data:
            self.queue.put_nowait(data)

    def stop(self) -> None:
        """
        Restore terminal settings and remove the reader callback.

        This leaves the terminal in its previous state.
        """
        self.loop.remove_reader(self.fd)
        if self._old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_settings)


class KeyDecoder:
    """
    Decode raw byte sequences to InputKey with support for exit/help.
    """

    def __init__(self, keymap: KeyMap) -> None:
        """
        Initialize decoder with mapping and precomputed prefixes.

        Keeps a buffer for partial sequences across reads.
        """
        self.mapping = keymap.mapping
        self.exit_sequences = keymap.exit_sequences
        self._buffer = b""
        all_sequences = set(self.mapping) | self.exit_sequences
        self._sequences = sorted(all_sequences, key=lambda s: (-len(s), s))
        self._prefixes = {seq[:i] for seq in all_sequences for i in range(1, len(seq))}

    def feed(self, chunk: bytes) -> list[tuple[bytes, InputKey | None]]:
        """
        Feed raw input bytes and return decoded key events.

        Emits (sequence, InputKey|None) tuples and buffers partial matches.
        """
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
