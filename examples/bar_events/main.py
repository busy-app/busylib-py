from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime

from busylib import exceptions
from busylib.client import AsyncBusyBar
from busylib.settings import settings


def _utc_now() -> str:
    """
    Return current UTC timestamp for event log prefixes.

    Seconds precision keeps output compact while preserving ordering.
    """
    return datetime.now(UTC).isoformat(timespec="seconds")


def _format_event(message: bytes | str) -> str:
    """
    Format one websocket message into readable single-line text.

    Text messages are normalized as JSON when possible; binary messages are
    rendered as byte length and hex payload for quick debugging.
    """
    if isinstance(message, bytes):
        return f"binary len={len(message)} hex={message.hex()}"

    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return f"text {message}"
    return f"json {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def _parse_args() -> argparse.Namespace:
    """
    Parse CLI options for input websocket monitoring.

    Arguments define the target device and optional event limit for finite
    captures used during debugging sessions.
    """
    parser = argparse.ArgumentParser(
        description="Print Busy Bar input events from /api/input websocket."
    )
    parser.add_argument(
        "--addr",
        default=settings.base_url,
        help="Busy Bar address (http://host or host).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="API token for Busy Bar HTTP API.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Stop after this many received events.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    """
    Connect to input websocket and stream events to stdout.

    The loop ends when websocket closes or when `--max-events` limit is
    reached, whichever happens first.
    """
    print(f"[{_utc_now()}] connect {args.addr} /api/input")
    received = 0
    async with AsyncBusyBar(addr=args.addr, token=args.token) as client:
        async for message in client.stream_input_events_ws():
            print(f"[{_utc_now()}] {_format_event(message)}")
            received += 1
            if args.max_events is not None and received >= args.max_events:
                return


def main() -> None:
    """
    Start input event monitor and handle Ctrl+C gracefully.

    Keyboard interrupts are transformed into a short terminal message.
    """
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except NotImplementedError as exc:
        print(f"[{_utc_now()}] not implemented: {exc}")
    except exceptions.BusyBarWebSocketError as exc:
        print(f"[{_utc_now()}] websocket error: {exc}")
        print("Hint: проверьте --addr; для защищенного API укажите --token.")
    except KeyboardInterrupt:
        print(f"[{_utc_now()}] stopped")


if __name__ == "__main__":
    main()
