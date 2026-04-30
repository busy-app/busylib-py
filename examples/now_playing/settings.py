from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class NowPlayingSettings(BaseSettings):
    """
    Runtime settings for the Now Playing showcase.

    The model reads environment variables and keeps CLI defaults consistent.
    """

    addr: str = "http://10.0.4.20"
    token: str | None = None
    source: Literal["lastfm", "json"] = "json"
    poll_interval_sec: float = 2.0
    app_id: str = "now-playing"
    display: Literal["front", "back"] = "front"
    title_color: str = "#FFFFFF"
    status_color: str = "#00E5FF"
    idle_title: str = "Nothing playing"
    idle_artist: str = "Waiting for track"
    once: bool = False

    lastfm_user: str | None = None
    lastfm_api_key: str | None = None

    json_path: Path = Path("examples/now_playing/sample_track.json")

    model_config = SettingsConfigDict(
        env_prefix="BUSYBAR_NOW_PLAYING_",
        extra="ignore",
    )


settings = NowPlayingSettings()
