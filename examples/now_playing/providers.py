from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import httpx

from .models import JsonTrackPayload, TrackState
from .settings import NowPlayingSettings


class TrackProvider(Protocol):
    """
    Contract for any Now Playing data source.

    Providers return a normalized track or None when no track is available.
    """

    async def fetch_current(self) -> TrackState | None:
        """
        Fetch and normalize the current track snapshot.

        Implementations should avoid raising for transient provider-side issues.
        """

    async def aclose(self) -> None:
        """
        Close provider resources if any were allocated.

        Providers without resources may implement this as a no-op.
        """


def _string_value(value: object) -> str | None:
    """
    Convert raw provider values to compact strings.

    The helper keeps JSON parsing code strict and explicit.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return None


def _extract_lastfm_track(payload: dict[str, object]) -> TrackState | None:
    """
    Parse Last.fm recent tracks payload into a normalized track model.

    The function returns None when payload structure is missing expected fields.
    """
    recent_tracks = payload.get("recenttracks")
    if not isinstance(recent_tracks, dict):
        return None

    tracks = recent_tracks.get("track")
    if not isinstance(tracks, list) or not tracks:
        return None

    first = tracks[0]
    if not isinstance(first, dict):
        return None

    name = _string_value(first.get("name"))
    artist_field = first.get("artist")
    artist_name: str | None = None
    if isinstance(artist_field, dict):
        artist_name = _string_value(artist_field.get("#text"))

    album_field = first.get("album")
    album_name: str | None = None
    if isinstance(album_field, dict):
        album_name = _string_value(album_field.get("#text"))

    attr = first.get("@attr")
    is_playing = False
    if isinstance(attr, dict):
        now_playing = _string_value(attr.get("nowplaying"))
        is_playing = now_playing == "true"

    mbid = _string_value(first.get("mbid"))

    if not name or not artist_name:
        return None

    return TrackState(
        source="lastfm",
        title=name,
        artist=artist_name,
        album=album_name,
        is_playing=is_playing,
        track_id=mbid,
    )


class LastFmProvider:
    """
    Provider fetching current track data from Last.fm user activity.

    It reads the latest entry from `user.getrecenttracks` and marks playback
    state based on `@attr.nowplaying`.
    """

    def __init__(
        self,
        user: str,
        api_key: str,
    ) -> None:
        """
        Initialize provider with Last.fm credentials.

        A dedicated async HTTP client is created for periodic polling.
        """
        self._user = user
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=10.0)

    async def fetch_current(self) -> TrackState | None:
        """
        Retrieve the most recent Last.fm track and normalize it.

        Network and schema errors resolve to None to keep the loop resilient.
        """
        try:
            response = await self._client.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "user.getrecenttracks",
                    "user": self._user,
                    "api_key": self._api_key,
                    "format": "json",
                    "limit": 1,
                },
            )
            response.raise_for_status()
            raw = response.json()
            if not isinstance(raw, dict):
                return None
            return _extract_lastfm_track(raw)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError):
            return None

    async def aclose(self) -> None:
        """
        Close the underlying async HTTP client.

        This prevents event loop warnings on process shutdown.
        """
        await self._client.aclose()


class JsonFileProvider:
    """
    Provider reading track data from a local JSON file.

    It is useful for demos and integration tests without external APIs.
    """

    def __init__(self, path: Path) -> None:
        """
        Store JSON file path used for polling.

        The file is parsed on each fetch to allow hot updates.
        """
        self._path = path

    async def fetch_current(self) -> TrackState | None:
        """
        Read and normalize track data from the configured JSON file.

        Invalid payloads and missing files return None instead of raising.
        """
        try:
            payload_raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload_raw, dict):
                return None
            payload = JsonTrackPayload.model_validate(payload_raw)
            return TrackState(
                source="json",
                title=payload.title,
                artist=payload.artist,
                album=payload.album,
                is_playing=payload.is_playing,
                track_id=payload.track_id,
            )
        except (FileNotFoundError, OSError, ValueError):
            return None

    async def aclose(self) -> None:
        """
        Close provider resources.

        The file-based provider keeps no resources and exits as a no-op.
        """
        return None


def build_provider(config: NowPlayingSettings) -> TrackProvider:
    """
    Create a provider instance according to runtime settings.

    The factory validates required source-specific credentials.
    """
    if config.source == "lastfm":
        if not config.lastfm_user or not config.lastfm_api_key:
            raise ValueError(
                "Last.fm source requires BUSYBAR_NOW_PLAYING_LASTFM_USER "
                "and BUSYBAR_NOW_PLAYING_LASTFM_API_KEY"
            )
        return LastFmProvider(
            user=config.lastfm_user,
            api_key=config.lastfm_api_key,
        )

    return JsonFileProvider(path=config.json_path)
