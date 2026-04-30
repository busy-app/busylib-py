# Now Playing Example

Show current track metadata on Busy Bar.

## Quick start (JSON source)

```bash
python -m examples.now_playing --source json --json-path examples/now_playing/sample_track.json
```

## Last.fm source

```bash
export BUSYBAR_NOW_PLAYING_SOURCE=lastfm
export BUSYBAR_NOW_PLAYING_LASTFM_USER=<your_user>
export BUSYBAR_NOW_PLAYING_LASTFM_API_KEY=<your_key>
python -m examples.now_playing --addr <busybar-ip> --token <token>
```

## Useful flags

- `--once` fetches and renders one snapshot then exits.
- `--display back` renders to the back display.
- `--poll-interval 1.0` sets custom polling interval.
