from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler

import httpx

from .constants import TEXT_ERR_CONNECT, TEXT_ERR_TIMEOUT, TEXT_STOPPED

DEBUG_SCREEN_CLEAR = True


def _clear_screen(reason: str, *, home: bool = False) -> None:
    """
    Clear the terminal screen and optionally reset cursor position.

    When debug is enabled, log the reason to stderr.
    """
    if DEBUG_SCREEN_CLEAR:
        sys.stderr.write(f"\n[remote] clear_screen: {reason}\n")
        sys.stderr.flush()

    sequence = "\x1b[2J"
    if home:
        sequence += "\x1b[H"
    print(sequence, end="")


def _clear_terminal() -> None:
    """
    Clear the terminal screen and reset cursor position.
    """
    _clear_screen("clear_terminal", home=True)


def _setup_logging(*, level: str, log_file: str | None) -> None:
    """
    Configure root logging with optional file output only.

    Console logging is intentionally disabled.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger_root = logging.getLogger()
    logger_root.handlers.clear()
    logger_root.setLevel(numeric_level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1_000_000,
            backupCount=0,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger_root.addHandler(file_handler)
    else:
        logger_root.addHandler(logging.NullHandler())


def _format_error_message(exc: BaseException) -> tuple[str | None, str]:
    """
    Convert common exceptions to a user-friendly message.

    Returns a (prefix, message) pair, where prefix can be None for plain output.
    """
    if isinstance(exc, KeyboardInterrupt):
        return None, TEXT_STOPPED

    message = str(exc)
    if "timed out during opening handshake" in message:
        return "Error", f"{TEXT_ERR_TIMEOUT} (WebSocket)"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "Error", TEXT_ERR_TIMEOUT
    if isinstance(exc, httpx.RequestError):
        return "Error", TEXT_ERR_CONNECT.format(details=message)
    if isinstance(exc, OSError):
        details = exc.strerror or message
        return "Error", TEXT_ERR_CONNECT.format(details=details)

    return "Error", message


def _print_user_message(
    prefix: str | None,
    message: str,
    *,
    addr: str | None = None,
) -> None:
    """
    Print a user-facing message without clearing the terminal.

    This resets ANSI state and ensures the error line is visible.
    """
    suffix = f" (addr: {addr})" if addr else ""
    sys.stderr.write("\n\x1b[0m\x1b[?25h")
    if prefix:
        sys.stderr.write(f"{prefix}: {message}{suffix}\n")
    else:
        sys.stderr.write(f"{message}{suffix}\n")
    sys.stderr.flush()


def _print_status_message(message: str) -> None:
    """
    Print a status message without clearing the terminal.

    This is used for startup and initialization updates.
    """
    sys.stderr.write("\n\x1b[0m\x1b[?25h")
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()
