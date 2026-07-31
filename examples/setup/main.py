from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from busylib.client import AsyncBusyBar

from examples.shared.discovery import resolve_connection
from examples.setup.prompts import SetupAborted, TerminalPrompt
from examples.setup.steps import default_steps
from examples.setup.wizard import run_setup


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the setup wizard.
    """
    parser = argparse.ArgumentParser(
        prog="setup",
        description=(
            "Walk a BUSY Bar through first-time setup: firmware, Wi-Fi, "
            "timezone, device name, and cloud account. Steps the device "
            "already satisfies are shown as done and skipped."
        ),
    )
    parser.add_argument(
        "addr_positional", nargs="?", default=None, help="Device address"
    )
    parser.add_argument("--addr", dest="addr", default=None, help="Device address")
    parser.add_argument("--token", default=None, help="Device access key")
    parser.add_argument(
        "--only",
        choices=[step.key for step in default_steps()],
        default=None,
        help="Run a single step instead of all pending ones",
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="Run steps even if the device already satisfies them",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Only print the checklist, changing nothing",
    )
    parser.add_argument("--log-level", default="WARNING", help="Logging level")

    args = parser.parse_args()
    if args.addr is None:
        args.addr = args.addr_positional
    return args


async def _run(args: argparse.Namespace) -> None:
    """
    Connect to the device and run the wizard.
    """
    prompt = TerminalPrompt()
    client = AsyncBusyBar(addr=args.addr, token=args.token)
    try:
        if args.status:
            from examples.setup.wizard import collect_status

            for report in await collect_status(client):
                prompt.info(report.render())
            return
        await run_setup(client, prompt, only=args.only, redo=args.redo)
    finally:
        await client.aclose()


def main() -> None:
    """
    Entry point for the standalone setup wizard.
    """
    args = parse_args()
    try:
        logging.basicConfig(level=args.log_level.upper())
        if args.addr is None:
            args.addr, args.token = resolve_connection(args.token)
        asyncio.run(_run(args))
    except (KeyboardInterrupt, SetupAborted):
        print("\nSetup cancelled.")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
