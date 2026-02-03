from __future__ import annotations

import json
from pathlib import Path

import pytest

from examples.remote.keymap import (
    KeyDecoder,
    _build_keymap,
    _encode_human_key,
    default_keymap,
    load_keymap,
)
from busylib.types import InputKey


def test_encode_human_key_variants() -> None:
    """
    Ensure human key specs map to expected byte sequences.
    Covers specials, control combos, and escape literals.
    """
    assert _encode_human_key("up") == b"\x1b[A"
    assert _encode_human_key("comma") == b","
    assert _encode_human_key("space") == b" "
    assert _encode_human_key("ctrl+a") == b"\x01"
    assert _encode_human_key("f1") == b"\x1bOP"
    assert _encode_human_key(r"\x1b[B") == b"\x1b[B"
    assert _encode_human_key("x") == b"x"


def test_default_keymap_has_variants_and_exit() -> None:
    """
    Validate default keymap includes common variants and exit sequence.
    Confirms arrow SS3 variants and enter newline handling.
    """
    keymap = default_keymap()
    assert keymap.mapping[b"\x1b[A"] is InputKey.UP
    assert keymap.mapping[b"\x1bOA"] is InputKey.UP
    assert keymap.mapping[b"\r"] is InputKey.OK
    assert keymap.mapping[b"\n"] is InputKey.OK
    assert keymap.mapping[b"\x1bOP"] is InputKey.BUSY
    assert keymap.mapping[b"\x1b[11~"] is InputKey.BUSY
    assert b"\x11" in keymap.exit_sequences


def test_load_keymap_from_file(tmp_path: Path) -> None:
    """
    Load a custom JSON keymap and ensure entries map correctly.
    """
    payload = {"k": "up", "j": "down", "esc": "back"}
    path = tmp_path / "keymap.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    keymap = load_keymap(path)
    assert keymap.mapping[b"k"] is InputKey.UP
    assert keymap.mapping[b"j"] is InputKey.DOWN
    assert keymap.mapping[b"\x1b"] is InputKey.BACK


def test_load_keymap_invalid_key_raises(tmp_path: Path) -> None:
    """
    Reject unknown InputKey names to keep the mapping strict.
    """
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"k": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown input key"):
        load_keymap(path)


def test_key_decoder_handles_prefixes_and_exit() -> None:
    """
    Decode multi-byte sequences across chunks and keep exit events.
    """
    keymap = _build_keymap({"up": InputKey.UP}, set(), set())
    decoder = KeyDecoder(keymap)

    assert decoder.feed(b"\x1b") == []
    events = decoder.feed(b"[A")
    assert events == [(b"\x1b[A", InputKey.UP)]

    keymap_exit = _build_keymap({"up": InputKey.UP}, set(), {"ctrl+q"})
    decoder_exit = KeyDecoder(keymap_exit)
    exit_events = decoder_exit.feed(b"\x11")
    assert exit_events == [(b"\x11", None)]
