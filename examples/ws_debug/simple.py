from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from urllib.parse import urlparse

import websockets

from busylib.settings import settings

logger = logging.getLogger(__name__)


def _build_ws_url(addr: str, token: str | None) -> str:
    """
    Build a websocket URL for the device screen endpoint.

    The token is appended as a query string when provided.
    """
    base = addr if "://" in addr else f"http://{addr}"
    parsed = urlparse(base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_base = parsed._replace(scheme=scheme).geturl().rstrip("/")
    url = f"{ws_base}/api/screen/ws"
    if token:
        url += f"?x-api-token={token}"
    return url


async def _run(args: argparse.Namespace) -> None:
    ws_url = _build_ws_url(args.addr, args.token)
    logger.info("Connecting to %s", ws_url)

    async with websockets.connect(
        ws_url,
        max_size=None,
        ping_interval=None,
    ) as ws:
        await ws.send(json.dumps({"display": args.display}))
        logger.info("Sent display selection %s", args.display)
        async for message in ws:
            if isinstance(message, bytes):
                logger.info("Frame bytes: %s", len(message))
                if args.once:
                    return
                continue
            logger.info("Text message len=%s", len(message))


def main() -> None:
    """
    Minimal WS debug client for screen streaming.
    """
    parser = argparse.ArgumentParser(description="WS debug client for Busy Bar.")
    parser.add_argument("--addr", default=settings.base_url, help="Device address.")
    parser.add_argument("--token", default=None, help="x-api-token value.")
    parser.add_argument("--display", type=int, default=0, help="Display index.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Read one frame then exit.",
    )
    parser.add_argument(
        "--log-level",
        default="DEBUG",
        help="Logging level.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.DEBUG),
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        logger.info("Stopped.")
        sys.exit(130)


if __name__ == "__main__":
    main()
