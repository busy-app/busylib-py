from __future__ import annotations

from busylib import types

from .models import TrackState
from .settings import NowPlayingSettings


def _status_text(track: TrackState) -> str:
    """
    Build a short status line for the current playback state.

    The text is intentionally compact to fit the front display width.
    """
    state = "PLAYING" if track.is_playing else "PAUSED"
    return f"{state} via {track.source}"


def track_signature(track: TrackState) -> tuple[str, str, str | None, bool, str | None]:
    """
    Return a stable signature for update deduplication.

    The runner uses this tuple to avoid redundant draw calls.
    """
    return (
        track.title,
        track.artist,
        track.album,
        track.is_playing,
        track.track_id,
    )


def render_track(
    track: TrackState,
    app_id: str,
    config: NowPlayingSettings,
) -> types.DisplayElements:
    """
    Convert a normalized track model into Busy Bar display elements.

    The layout uses three text lines: title, artist, and playback status.
    """
    display_name = types.DisplayName.FRONT
    if config.display == "back":
        display_name = types.DisplayName.BACK

    elements: list[types.TextElement] = [
        types.TextElement(
            id="title",
            x=0,
            y=0,
            text=track.title,
            font="small",
            align="top_left",
            color=config.title_color,
            width=72,
            scroll_rate=20,
            display=display_name,
        ),
        types.TextElement(
            id="artist",
            x=0,
            y=8,
            text=track.artist,
            font="small",
            align="top_left",
            color=config.title_color,
            width=72,
            scroll_rate=20,
            display=display_name,
        ),
        types.TextElement(
            id="status",
            x=0,
            y=15 if config.display == "back" else 0,
            text=_status_text(track),
            font="small",
            align="bottom_left" if config.display == "back" else "top_left",
            color=config.status_color,
            width=72,
            scroll_rate=20,
            display=display_name,
        ),
    ]

    return types.DisplayElements(app_id=app_id, elements=elements)


def render_idle(config: NowPlayingSettings) -> types.DisplayElements:
    """
    Build an idle view shown when no track data is available.

    This keeps the display informative even when providers return nothing.
    """
    display_name = types.DisplayName.FRONT
    if config.display == "back":
        display_name = types.DisplayName.BACK

    elements: list[types.TextElement] = [
        types.TextElement(
            id="idle-title",
            x=0,
            y=0,
            text=config.idle_title,
            font="small",
            align="top_left",
            color=config.title_color,
            width=72,
            scroll_rate=20,
            display=display_name,
        ),
        types.TextElement(
            id="idle-subtitle",
            x=0,
            y=8,
            text=config.idle_artist,
            font="small",
            align="top_left",
            color=config.status_color,
            width=72,
            scroll_rate=20,
            display=display_name,
        ),
    ]
    return types.DisplayElements(app_id=config.app_id, elements=elements)
