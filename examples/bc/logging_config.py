from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler


def configure_logging(
    *,
    level: str,
    log_file: str | None,
) -> None:
    """
    Configure root logging to write only to a specified file.

    When no file is provided, attach a null handler to suppress output.
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
            backupCount=1,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(fmt)
        logger_root.addHandler(file_handler)
    else:
        logger_root.addHandler(logging.NullHandler())


def _configure_logging(
    *,
    level: str,
    log_file: str | None,
) -> None:
    """
    Backward-compatible wrapper for logging setup.

    Keeps older imports working while delegating to configure_logging.
    """
    configure_logging(level=level, log_file=log_file)
