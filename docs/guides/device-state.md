# Reading device state

## A one-off snapshot

For a quick look at everything at once, `collect_device_snapshot` gathers the
individual endpoints concurrently and tolerates partial failures:

```python
from busylib.features import collect_device_snapshot

snapshot = await collect_device_snapshot(client)
print(snapshot.name, snapshot.power, snapshot.wifi)
print(snapshot.field_errors)  # whatever could not be read, and why
```

A field that fails lands in `field_errors` instead of aborting the whole
snapshot, so one unavailable endpoint doesn't cost you the rest.

The underlying calls are available individually too: `version()`, `status()`,
`display_brightness()`, `audio_volume()`, `wifi_status()`, `ble_status()`,
`storage_status()`, `time()`, `name()`.

## Streaming updates

`/api/status/ws` pushes protobuf state messages as things change, which is far
better than polling:

```python
async for message in client.stream_status_ws():
    if isinstance(message, dict):
        print(message)
```

Messages are decoded from the `BSB_State.State` schema into dictionaries with
the original proto field names. Each one carries a list of `updates`, where
every entry is one changed thing: `device_name`, `power`, `brightness`,
`audio_volume`, `wifi`, `timezone`, `ble`, `update_state`, `input`, `timer`, or
`frame`.

## Keeping a snapshot in sync

`DeviceStateStore` applies those deltas onto a snapshot for you and notifies
subscribers:

```python
from busylib.features import DeviceStateStore, collect_device_snapshot

store = DeviceStateStore(await collect_device_snapshot(client))
store.on_state(lambda snapshot: print("now:", snapshot.name))
store.on_diff(lambda changed, snapshot: print("changed:", changed))

async for message in client.stream_status_ws():
    if isinstance(message, dict):
        store.apply_stream_message(message)
```

`on_state` receives the full updated snapshot; `on_diff` also receives the set
of top-level fields that actually changed, which is handy for redrawing only
what moved.

## Screen frames arrive here too

Current firmware has no separate screen WebSocket. Instead, front-display
frames come through this same stream as `frame` updates, carrying their own
`width`, `height`, `encoding`, and `pixel_format`. The store decodes them into
RGB888 bytes on `DeviceSnapshot.screen_front` and `screen_back`:

```python
def on_diff(changed, snapshot):
    if "screen_front" in changed and snapshot.screen_front is not None:
        render(snapshot.screen_front)

store.on_diff(on_diff)
```

Because the frame describes its own encoding, no guessing by payload size is
involved — see `busylib.display.decode_frame_data`. A decoded frame whose size
doesn't match the target display is logged and dropped rather than stored, so a
malformed update can't reach a renderer.
