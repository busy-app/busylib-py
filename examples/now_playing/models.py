from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TrackState(BaseModel):
    """
    Normalized representation of a currently known track state.

    The model is provider-agnostic and is used by renderer and runner layers.
    """

    source: str
    title: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    album: str | None = None
    is_playing: bool = True
    track_id: str | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class JsonTrackPayload(BaseModel):
    """
    JSON payload shape accepted by the local file provider.

    It allows quick local testing without integrating with a music API.
    """

    title: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    album: str | None = None
    is_playing: bool = True
    track_id: str | None = None
