from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import os
import sys
from urllib.parse import urlparse

from busylib import AsyncBusyBar

logger = logging.getLogger(__name__)


DEFAULT_LAN_TOKEN = "5422"
DEFAULT_WS_ADDR = "http://10.0.4.20"


def _default_addr() -> str:
    """
    Return the default device address for ws_debug.

    Respects BUSY_ADDR when provided, otherwise uses DEFAULT_WS_ADDR.
    """
    return os.getenv("BUSY_ADDR", DEFAULT_WS_ADDR)


def _build_client(addr: str, token_arg: str | None) -> AsyncBusyBar:
    """
    Build an AsyncBusyBar client with LAN/cloud token resolution.

    Uses BUSY_LAN_TOKEN for private addresses or BUSY_CLOUD_TOKEN otherwise.
    Falls back to DEFAULT_LAN_TOKEN for private addresses when no env is set.
    """
    base_addr = addr if addr.startswith(("http://", "https://")) else f"http://{addr}"
    parsed = urlparse(base_addr)
    host = parsed.hostname or ""
    token = token_arg
    extra_headers: dict[str, str] = {}

    if token is None:
        try:
            ip = ipaddress.ip_address(host)
            is_private = ip.is_private
        except ValueError:
            is_private = host.endswith(".local") or host.startswith("localhost")

        if is_private:
            lan_token = os.getenv("BUSY_LAN_TOKEN") or os.getenv("BUSYLIB_LAN_TOKEN")
            if lan_token:
                extra_headers["x-api-token"] = lan_token
            else:
                extra_headers["x-api-token"] = DEFAULT_LAN_TOKEN
        if not extra_headers:
            cloud_token = os.getenv("BUSY_CLOUD_TOKEN")
            if cloud_token:
                token = cloud_token

    client = AsyncBusyBar(addr=base_addr, token=token)
    if extra_headers:
        client.client.headers.update(extra_headers)
    return client


async def _run(args: argparse.Namespace) -> None:
    """
    Connect via AsyncBusyBar and log incoming WS frames.

    Sends the display selection and reads frames until stopped.
    """
    client = _build_client(args.addr, args.token)
    logger.info("Connecting to %s via AsyncBusyBar", client.base_url)
    logger.info("Sent display selection %s", args.display)
    try:
        async for message in client.stream_screen_ws(args.display):
            if isinstance(message, bytes):
                logger.info("Frame bytes: %s", len(message))
                if args.once:
                    return
                continue
            logger.info("Text message len=%s", len(message))
    finally:
        await client.aclose()


def main() -> None:
    """
    Minimal WS debug client for screen streaming.
    """
    parser = argparse.ArgumentParser(description="WS debug client for Busy Bar.")
    parser.add_argument("--addr", default=_default_addr(), help="Device address.")
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
