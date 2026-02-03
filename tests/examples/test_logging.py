from __future__ import annotations

import contextlib
from collections.abc import Iterator
import logging
from pathlib import Path

from examples.bc import logging_config as bc_logging
from examples.remote import terminal_utils as remote_terminal


@contextlib.contextmanager
def _preserve_root_logging() -> Iterator[None]:
    """
    Preserve root logging handlers and level across a test.
    This keeps logging configuration isolated from other tests.
    """
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    try:
        yield
    finally:
        root.handlers.clear()
        root.handlers.extend(handlers)
        root.setLevel(level)


def _has_console_handler(handlers: list[logging.Handler]) -> bool:
    """
    Detect a non-file stream handler that would log to console.
    File handlers are excluded from this check.
    """
    return any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in handlers
    )


def test_remote_logging_file_only(tmp_path: Path) -> None:
    """
    Ensure remote logging writes only to a specified file.
    Console handlers should be absent when log_file is set.
    """
    with _preserve_root_logging():
        log_path = tmp_path / "remote.log"
        remote_terminal._setup_logging(level="INFO", log_file=str(log_path))
        handlers = logging.getLogger().handlers
        assert any(
            isinstance(handler, logging.handlers.RotatingFileHandler)
            for handler in handlers
        )
        assert not any(isinstance(handler, logging.NullHandler) for handler in handlers)
        assert not _has_console_handler(handlers)


def test_remote_logging_null_when_disabled() -> None:
    """
    Ensure remote logging is fully silenced without a log file.
    A null handler prevents console output.
    """
    with _preserve_root_logging():
        remote_terminal._setup_logging(level="INFO", log_file=None)
        handlers = logging.getLogger().handlers
        assert any(isinstance(handler, logging.NullHandler) for handler in handlers)
        assert not any(isinstance(handler, logging.FileHandler) for handler in handlers)
        assert not _has_console_handler(handlers)


def test_bc_logging_file_only(tmp_path: Path) -> None:
    """
    Ensure bc logging writes only to a specified file.
    Console handlers should be absent when log_file is set.
    """
    with _preserve_root_logging():
        log_path = tmp_path / "bc.log"
        bc_logging._configure_logging(
            level="INFO",
            log_file=str(log_path),
        )
        handlers = logging.getLogger().handlers
        assert any(
            isinstance(handler, logging.handlers.RotatingFileHandler)
            for handler in handlers
        )
        assert not any(isinstance(handler, logging.NullHandler) for handler in handlers)
        assert not _has_console_handler(handlers)


def test_bc_logging_null_when_disabled() -> None:
    """
    Ensure bc logging is fully silenced without a log file.
    A null handler prevents console output.
    """
    with _preserve_root_logging():
        bc_logging._configure_logging(
            level="INFO",
            log_file=None,
        )
        handlers = logging.getLogger().handlers
        assert any(isinstance(handler, logging.NullHandler) for handler in handlers)
        assert not any(isinstance(handler, logging.FileHandler) for handler in handlers)
        assert not _has_console_handler(handlers)
