from __future__ import annotations

import json
import sys
import termios
from pathlib import Path


def disable_flow_control() -> list[int]:
    """
    Disable terminal XON/XOFF flow control.

    Returns original termios attributes to restore later.
    """
    fd = sys.stdin.fileno()
    attrs = termios.tcgetattr(fd)
    new_attrs = attrs[:]
    new_attrs[3] = new_attrs[3] & ~termios.IXON  # lflags: disable XON/XOFF
    termios.tcsetattr(fd, termios.TCSANOW, new_attrs)
    return attrs


def restore_term(attrs: list[int]) -> None:
    """
    Restore terminal settings after flow-control changes.

    Ignores failures to avoid blocking on shutdown.
    """
    try:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, attrs)
    except Exception:
        pass


def state_path() -> Path:
    """
    Return the filesystem path to the saved UI state file.

    Uses the user's home directory for persistence across runs.
    """
    return Path.home() / ".busylib_bc_state.json"


def load_state() -> dict[str, str | bool]:
    """
    Load UI state from disk.

    Returns an empty dict on missing file or invalid content.
    """
    path = state_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(local_cwd: str, remote_cwd: str, active_left: bool) -> None:
    """
    Persist UI state to disk.

    Best-effort write with a minimal JSON payload.
    """
    try:
        state_path().write_text(
            json.dumps(
                {
                    "local_cwd": local_cwd,
                    "remote_cwd": remote_cwd,
                    "active_left": active_left,
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
