from __future__ import annotations

from examples.remote import terminal_utils as remote_terminal


def test_clear_terminal_writes_escape(capsys) -> None:
    """
    Ensure terminal clear helper prints the expected escape sequence.
    """
    remote_terminal._clear_terminal()
    captured = capsys.readouterr()
    assert captured.out == "\x1b[2J\x1b[H"
