from __future__ import annotations

import asyncio
import logging

from busylib.client import AsyncBusyBar

from .providers import TrackProvider
from .renderer import render_idle, render_track, track_signature
from .settings import NowPlayingSettings

logger = logging.getLogger(__name__)


async def run_now_playing(
    client: AsyncBusyBar,
    provider: TrackProvider,
    config: NowPlayingSettings,
) -> None:
    """
    Run polling loop and render track updates to Busy Bar.

    The loop sends draw requests only when track payload actually changed.
    """
    last_signature: tuple[str, str, str | None, bool, str | None] | None = None
    idle_sent = False

    while True:
        track = await provider.fetch_current()

        if track is None:
            if not idle_sent:
                await client.draw_on_display(render_idle(config))
                idle_sent = True
                last_signature = None
                logger.info("Rendered idle now-playing view")
        else:
            current_signature = track_signature(track)
            if current_signature != last_signature:
                await client.draw_on_display(
                    render_track(
                        track=track,
                        app_id=config.app_id,
                        config=config,
                    )
                )
                last_signature = current_signature
                idle_sent = False
                logger.info(
                    "Rendered track: %s - %s (playing=%s)",
                    track.artist,
                    track.title,
                    track.is_playing,
                )

        if config.once:
            return

        await asyncio.sleep(config.poll_interval_sec)
