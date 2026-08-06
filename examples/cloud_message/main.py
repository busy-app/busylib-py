from __future__ import annotations

import argparse
import logging
import os
import sys

from busylib import exceptions

from examples.cloud_message.cloud import CLOUD_BASE_URL, CloudBar
from examples.cloud_message.colors import NAMED_COLORS, ColorError
from examples.cloud_message.message import (
    APPLICATION_NAME,
    DEFAULT_BACKGROUND_ALPHA,
    DEFAULT_PRIORITY,
    Message,
    build_elements,
)

TOKEN_ENV_VAR = "BUSY_BAR_TOKEN"

FONTS = [
    "tiny",
    "small",
    "normal",
    "condensed",
    "bold",
    "large",
    "extra_large",
    "global",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Parse CLI arguments for the cloud message example.
    """
    background_percent = DEFAULT_BACKGROUND_ALPHA * 100 // 255
    parser = argparse.ArgumentParser(
        prog="cloud_message",
        description=(
            "Show a status message on a BUSY Bar over the internet. The bar "
            "does not need to be on the same network: requests go through the "
            f"cloud service at {CLOUD_BASE_URL}. Requires an API token with "
            "the 'BUSY Bar' access scope, created at https://cloud.busy.app."
        ),
    )
    parser.add_argument("text", nargs="?", help="Message text (printable ASCII)")
    parser.add_argument(
        "--token",
        default=None,
        help=f"API token; defaults to the {TOKEN_ENV_VAR} environment variable",
    )
    parser.add_argument("--color", default="white", help="Text color")
    parser.add_argument(
        "--background",
        default=None,
        help=(
            "Translucent color overlay, e.g. 'red' or 'red@40'. Bare names get "
            f"{background_percent}%% alpha, because an opaque fill hides the text"
        ),
    )
    parser.add_argument("--led", default=None, help="Status LED blink color")
    parser.add_argument("--font", choices=FONTS, default="normal", help="Font name")
    parser.add_argument(
        "--no-scroll", action="store_true", help="Do not scroll long text"
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=DEFAULT_PRIORITY,
        help=(
            f"Draw priority 1-100 (default {DEFAULT_PRIORITY}, which preempts "
            "an active work session at 90)"
        ),
    )
    parser.add_argument(
        "--clear", action="store_true", help="Clear this app's elements and exit"
    )
    parser.add_argument(
        "--status", action="store_true", help="Print device status and exit"
    )
    parser.add_argument(
        "--list-colors", action="store_true", help="List color names and exit"
    )
    parser.add_argument("--log-level", default="WARNING", help="Logging level")
    return parser.parse_args(argv)


def resolve_token(explicit: str | None) -> str:
    """
    Return the API token from the CLI flag or the environment.
    """
    token = explicit or os.environ.get(TOKEN_ENV_VAR)
    if not token:
        raise SystemExit(
            f"No API token. Pass --token or set {TOKEN_ENV_VAR}.\n"
            "Create one at https://cloud.busy.app with the 'BUSY Bar' access "
            "scope; an 'account'-scoped token is rejected with 403."
        )
    return token


def main(argv: list[str] | None = None) -> int:
    """
    Run the cloud message example.
    """
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level.upper())

    if args.list_colors:
        for name in sorted(NAMED_COLORS):
            print(f"  {name:9s} #{NAMED_COLORS[name]}")
        return 0

    if not args.clear and not args.status and not args.text:
        raise SystemExit("Provide message text, or use --clear or --status.")

    # Validate everything before touching the device.
    message: Message | None = None
    if args.text and not args.clear:
        try:
            message = Message(
                text=args.text,
                color=args.color,
                background=args.background,
                led=args.led,
                font=args.font,
                scroll=not args.no_scroll,
                priority=args.priority,
            )
            elements = build_elements(message)
        except (ColorError, ValueError) as exc:
            raise SystemExit(f"Invalid message: {exc}") from None

    token = resolve_token(args.token)

    try:
        with CloudBar(token) as bar:
            if args.status:
                print(bar.status())
                return 0
            if args.clear:
                bar.clear(APPLICATION_NAME)
                print("cleared")
                return 0
            assert message is not None
            bar.draw(elements)
            print(f"posted: {message.text}")
    except exceptions.BusyBarAPIError as exc:
        if exc.status_code == 403:
            raise SystemExit(
                "403 Forbidden: the token was not accepted for this bar. "
                "Check that it has the 'BUSY Bar' access scope rather than "
                "'account', and that the bar is linked to the same account."
            ) from None
        if exc.status_code == 409:
            raise SystemExit(
                f"409 Conflict: priority {args.priority} is below the app "
                "currently on screen. Retry with a higher --priority."
            ) from None
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
