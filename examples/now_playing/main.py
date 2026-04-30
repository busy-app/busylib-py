from __future__ import annotations

import argparse
import asyncio
import logging

from busylib.client import AsyncBusyBar

from .providers import build_provider
from .runner import run_now_playing
from .settings import NowPlayingSettings


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the Now Playing showcase.

    CLI values override environment-derived defaults from settings.
    """
    parser = argparse.ArgumentParser(description="Busy Bar Now Playing showcase")
    parser.add_argument("--addr", default=None, help="Busy Bar address")
    parser.add_argument("--token", default=None, help="Busy Bar API token")
    parser.add_argument(
        "--source",
        choices=["lastfm", "json"],
        default=None,
        help="Track source backend",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--json-path",
        default=None,
        help="JSON file path for --source json",
    )
    parser.add_argument("--lastfm-user", default=None, help="Last.fm username")
    parser.add_argument("--lastfm-api-key", default=None, help="Last.fm API key")
    parser.add_argument(
        "--display",
        choices=["front", "back"],
        default=None,
        help="Target Busy Bar display",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch and render one snapshot, then exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level",
    )
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> NowPlayingSettings:
    """
    Merge environment settings with CLI overrides.

    The function keeps all runtime defaults in one strongly typed model.
    """
    base = NowPlayingSettings()
    updates: dict[str, object] = {}

    if args.addr is not None:
        updates["addr"] = args.addr
    if args.token is not None:
        updates["token"] = args.token
    if args.source is not None:
        updates["source"] = args.source
    if args.poll_interval is not None:
        updates["poll_interval_sec"] = args.poll_interval
    if args.json_path is not None:
        updates["json_path"] = args.json_path
    if args.lastfm_user is not None:
        updates["lastfm_user"] = args.lastfm_user
    if args.lastfm_api_key is not None:
        updates["lastfm_api_key"] = args.lastfm_api_key
    if args.display is not None:
        updates["display"] = args.display
    if args.once:
        updates["once"] = True

    return base.model_copy(update=updates)


async def _run(args: argparse.Namespace) -> None:
    """
    Initialize provider/client and execute the now-playing loop.

    Resources are closed in `finally` blocks to avoid leaking connections.
    """
    config = _build_config(args)
    provider = build_provider(config)
    client = AsyncBusyBar(addr=config.addr, token=config.token)

    try:
        await run_now_playing(
            client=client,
            provider=provider,
            config=config,
        )
    finally:
        await provider.aclose()
        await client.client.aclose()


def main() -> None:
    """
    Start the showcase with optional CLI overrides.

    Logging is configured before async startup for consistent diagnostics.
    """
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
