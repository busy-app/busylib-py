from __future__ import annotations

import argparse
import asyncio
import sys

from examples.remote.runner import _run as runner
from examples.remote.constants import (
    DEFAULT_LOG_LEVEL,
    ICON_SETS,
    TEXT_ARG_ADDR,
    TEXT_ARG_DESC,
    TEXT_ARG_FRAME,
    TEXT_ARG_HTTP,
    TEXT_ARG_KEYMAP,
    TEXT_ARG_LOG_FILE,
    TEXT_ARG_LOG_LEVEL,
    TEXT_ARG_NO_INPUT,
    TEXT_ARG_SPACER,
    TEXT_ARG_TOKEN,
)
from examples.remote.settings import settings
from examples.remote.terminal_utils import (
    _clear_screen,
    _clear_terminal,
    _enter_fullscreen,
    _exit_fullscreen,
    _format_error_message,
    _print_status_message,
    _print_user_message,
    _setup_logging,
)


def _select_icon_set(mode: str) -> dict[str, str]:
    """
    Select the icon set for the terminal UI.

    Unknown modes fall back to the emoji icon set.
    """
    normalized = mode.strip().lower()
    return ICON_SETS.get(normalized, ICON_SETS["emoji"])


ICONS = _select_icon_set(settings.icon_mode)
PIXEL_CHAR = ICONS["pixel"]


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for streaming and input forwarding.
    Keep defaults aligned with file-only logging.
    """
    parser = argparse.ArgumentParser(description=TEXT_ARG_DESC)
    parser.add_argument("--addr", default=None, help=TEXT_ARG_ADDR)
    parser.add_argument("--token", default=None, help=TEXT_ARG_TOKEN)
    parser.add_argument(
        "--http-poll-interval",
        type=float,
        default=None,
        help=TEXT_ARG_HTTP,
    )
    parser.add_argument(
        "--spacer",
        type=str,
        default=settings.spacer,
        help=TEXT_ARG_SPACER,
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        help=TEXT_ARG_LOG_LEVEL,
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help=TEXT_ARG_LOG_FILE,
    )
    parser.add_argument(
        "--no-send-input",
        action="store_true",
        help=TEXT_ARG_NO_INPUT,
    )
    parser.add_argument(
        "--keymap-file",
        type=str,
        default=None,
        help=TEXT_ARG_KEYMAP,
    )
    parser.add_argument(
        "--frame",
        choices=["full", "horizontal", "none"],
        default=settings.frame_mode,
        help=TEXT_ARG_FRAME,
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    """
    Run the remote streaming loop with renderer and CLI options.

    Delegates the heavy lifting to the runner module.
    """
    _setup_logging(level=args.log_level, log_file=args.log_file)
    _enter_fullscreen()
    try:
        await runner(
            args,
            icons=ICONS,
            clear_screen=_clear_screen,
            clear_terminal=_clear_terminal,
            status_message=_print_status_message,
        )
    finally:
        _exit_fullscreen()


def main() -> None:
    """
    Entry point for remote screen streaming.
    """
    args = None
    try:
        args = parse_args()
        asyncio.run(_run(args))
    except KeyboardInterrupt as exc:
        prefix, message = _format_error_message(exc)
        _print_user_message(
            prefix,
            message,
            addr=None if args is None else getattr(args, "addr", None),
        )
        sys.exit(130)
    except Exception as exc:
        prefix, message = _format_error_message(exc)
        _print_user_message(
            prefix,
            message,
            addr=None if args is None else getattr(args, "addr", None),
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
