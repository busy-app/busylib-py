# Now Playing

`Now Playing` is the primary showcase scenario for the documentation.

## Goal

Display current track metadata (title, artist, playback state) on Busy Bar and keep it updated with low latency.

## End-to-End Flow

1. Fetch current track data from a music source (for example Spotify/Last.fm bridge).
2. Normalize metadata into a stable internal model.
3. Map metadata into Busy Bar display elements.
4. Push updates only when track state changes.

## Why This Example

- It demonstrates integration with an external API.
- It exercises periodic refresh + delta updates.
- It reflects a practical consumer use case.

## Related API Reference

- [Core Client](../api/core-client.md)
- [Now Playing Example API](../api/now-playing-example.md)

## Status

The production-ready example is available in `examples/now_playing/`.

## Run With Local JSON

```bash
python -m examples.now_playing --source json --json-path examples/now_playing/sample_track.json
```

## Run With Last.fm

```bash
export BUSYBAR_NOW_PLAYING_SOURCE=lastfm
export BUSYBAR_NOW_PLAYING_LASTFM_USER=<your_user>
export BUSYBAR_NOW_PLAYING_LASTFM_API_KEY=<your_key>
python -m examples.now_playing --addr <busybar-ip> --token <token>
```
