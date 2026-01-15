from __future__ import annotations

import argparse
import curses
import os
import sys

from busylib.client import AsyncBusyBar

from .client_factory import build_client
from .logging_config import _configure_logging
from .runner import AsyncRunner
from .startup import ensure_app_directory
from .ui import run_ui


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the BusyBar browser.

    Defines address, token, and logging options.
    """
    parser = argparse.ArgumentParser(description="BusyBar MC-like browser.")
    parser.add_argument(
        "--addr",
        default=os.getenv("BUSY_ADDR", "http://10.0.4.20"),
        help="BusyBar address.",
    )
    parser.add_argument(
        "--token", default=os.getenv("BUSY_TOKEN"), help="Bearer token."
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--log-file", default=None, help="Log file path.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=True,
        help="Disable console logs (default: quiet).",
    )
    parser.add_argument(
        "--app",
        default="bc",
        help="App id used for /ext/assets/<app> directory.",
    )
    return parser.parse_args()


def run_client(client: AsyncBusyBar, runner: AsyncRunner, *, app: str) -> None:
    """
    Run the UI with a prepared client and runner.

    Ensures the client is closed and runner stopped on exit.
    """
    runner.start(client)
    runner.run(client.list_storage_files("/ext"))
    app_dir = ensure_app_directory(runner, app)
    try:
        curses.wrapper(run_ui, client, runner, app_dir=app_dir)
    finally:
        runner.run(client.aclose())
        runner.stop()


def main() -> None:
    """
    Entry point for the BusyBar MC-like browser.

    Builds the client, configures logging, and starts the UI.
    """
    try:
        args = parse_args()
        _configure_logging(level=args.log_level, log_file=args.log_file)
        client = build_client(args.addr, args.token)
        runner = AsyncRunner()
        run_client(client, runner, app=args.app)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
