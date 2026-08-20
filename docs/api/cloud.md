# Cloud addresses

The BUSY cloud publishes two separate APIs on one host, and they are not
interchangeable — a token for one is refused by the other.

| Surface | Address | Token | In this library |
| --- | --- | --- | --- |
| Device API | [`/busybar`](https://api.busy.app/busybar/docs) | bar-scope | yes, as cloud mode |
| Account API | [`/`](https://api.busy.app/docs) | account-scope | no |

## Choosing an environment

A bar can be pointed at a non-production cloud, and a client has to follow it
there. Name the host and say that it is a cloud:

```python
bb = BusyBar(
    addr="https://api.dev.busy.app",
    token="<bar-scope token for that environment>",
    is_cloud=True,
)
```

`is_cloud` matters. Without it the address is taken for a device, so requests
go to `/api` with the device's token header instead of `/busybar` with a
bearer one, and fail without explaining themselves. Omitting `addr` still
means the configured cloud host, so `BusyBar(token=...)` is unchanged; the
default comes from `BUSYLIB_CLOUD_URL`.

The helpers below follow the same host, so a bar on a development cloud gets
that environment's documentation rather than production's. Both accept an
explicit `host` if you need to ask about another one.

Cloud mode talks to the device API. It is the same set of endpoints a bar
serves locally, with `/api` replaced by `/busybar`, so every client method
works unchanged:

```python
from busylib import BusyBar

bb = BusyBar(token="<bar-scope token>")  # no address means cloud
print(bb.version().api_semver)
```

Status streaming is the one exception: `/api/status/ws` is local only, and
cloud mode refuses it rather than attempting an upgrade the cloud rejects.

## Documentation per firmware version

The device documentation is versioned, selected by **firmware** version —
`1.1.1`, not the API version `25.0.0`. A bar reports its firmware under
`status().firmware.version`, which gives you the page describing what that
particular bar serves:

::: busylib.cloud.device_docs_url
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3

The same document is available machine-readable, which is how you can ask
what a firmware supports without having that bar to hand:

::: busylib.cloud.device_spec_url
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3

Putting the two together, this links a connected bar to its own reference:

```python
from busylib import BusyBar, cloud

with BusyBar("10.0.4.20") as bb:
    firmware = bb.status().firmware
    print(cloud.device_docs_url(firmware.version if firmware else None))
```

## Why these live in code

These addresses move. The cloud host was renamed before launch while this
library kept the old name, and cloud mode was unusable for months as a
result. Importing them from `busylib.cloud` means a rename is one edit rather
than a search through guides and docstrings.
