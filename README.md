# busylib

[![PyPI version](https://img.shields.io/pypi/v/busylib.svg?label=PyPI)](https://pypi.org/project/busylib/)
[![Python versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/busylib/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/busy-app/busylib-py/blob/main/LICENSE)

A Python client for the BUSY Bar API. Draw on both displays, play audio, manage
files and assets, read device state, and forward input — from a script instead
of the device UI.

## You just unboxed a BUSY Bar

This guide takes you from a bar still in its box to a small working app.

Bars ship with **firmware 1.0.2**. Plug one into your computer over USB and it
comes up as a network device at **`10.0.4.20`** — no Wi-Fi setup needed yet.
Open <http://10.0.4.20> in a browser and you'll get the bar's own web UI, which
is a good way to confirm the connection before writing any code.

Everything that UI does is the same HTTP API this library speaks, so anything
you can click there you can also script.

> **Update the firmware early.** Firmware 1.0.2 serves API version `24.3.0`,
> while this library targets `25.0.0`. Most things still work, but you'll see
> compatibility warnings and a few newer methods are unavailable. The setup
> wizard below handles updating for you.

## Installation

```bash
pip install busylib
```

Upgrade to the latest release:

```bash
pip install --upgrade busylib
```

## Step 1 — Connect over USB

With the bar plugged in, check that it answers:

```python
from busylib import BusyBar

bb = BusyBar("10.0.4.20")
print(bb.version())
```

Current firmware enforces its access key only on connections arriving over
Wi-Fi, so a bar reached over USB usually needs no token. If you do get a
`403 Forbidden` here, pass the key as a token the same way as below.

Once the bar is on Wi-Fi you can use its Wi-Fi address instead, or let the
library find it for you — see [Discovering devices](#discovering-devices-on-the-network).
That path *can* answer `403 Forbidden`, which means an access key is set —
a 4–10 digit PIN, the same one the web UI asks for:

```python
bb = BusyBar("192.168.1.20", token="1234")
```

## Step 2 — First-time setup

The examples below ship with the source rather than the PyPI package, so grab
a clone to run them:

```bash
git clone https://github.com/busy-app/busylib-py
cd busylib-py
```

Rather than clicking through the device UI, run the setup wizard. It reads the
bar's current state, shows you what's already configured, and only asks about
what's missing:

```bash
uv run python -m examples.setup.main 10.0.4.20
```

```
BUSY Bar setup
  [ ] Firmware       1.0.2 (API 24.3.0) - library targets API 25.0.0
  [ ] Wi-Fi          disconnected
  [ ] Timezone       UTC+00:00 - this computer is UTC+03:00
  [ ] Device name    BUSY Bar (factory default)
  [ ] Cloud account  not linked
```

It walks through firmware update, Wi-Fi, timezone, device name, and linking the
bar to a BUSY cloud account. Steps already done are marked `[x]` and skipped, so
it's safe to re-run at any time — for example after the bar reboots into new
firmware.

Useful flags:

| Flag | Effect |
| --- | --- |
| `--status` | Print the checklist and change nothing |
| `--only <step>` | Run one step: `firmware`, `wifi`, `timezone`, `name`, `cloud` |
| `--redo` | Run steps even if they're already done |

The same wizard is available as the `setup` command inside the interactive
`remote` example, so you can re-run it without leaving that view.

## Step 3 — Your first app

Now let's build something small: a status light that writes on the front
display, shows an icon on the back one, and plays a sound.

Two things to know before you start:

- The **front** display is a **72×16** RGB LED matrix. The **back** display is
  **160×80**, 16 shades of grey. Elements placed outside those bounds simply
  won't be visible, so keep coordinates inside them.
- Every element needs an `id` and belongs to an `application_name`, which is how
  the bar groups what your app draws.

### 3.1 Say hello on the front display

```python
from busylib import BusyBar, types

bb = BusyBar("10.0.4.20")

bb.display_draw(
    types.DisplayElements(
        application_name="my-app",
        elements=[
            types.TextElement(
                id="status",
                type="text",
                x=2,
                y=4,
                text="BUILDING",
                font="small",
                display=types.DisplayName.FRONT,
            ),
        ],
    )
)
```

Available fonts are `tiny`, `small`, `normal`, `condensed`, `bold`, `large`,
`extra_large`, and `global`.

### 3.2 Add a picture

Images and audio have to be uploaded to the bar before you can reference them.
Note that `assets_upload` sends bytes as-is — it does **not** convert them, so
resize and re-encode the file for the target display first:

```python
from busylib import converter

with open("icon.png", "rb") as f:
    filename, payload = converter.convert_for_storage("icon.png", f.read())

bb.assets_upload(
    application_name="my-app",
    filename=filename,
    data=payload,
)
```

`convert_for_storage` scales and crops the image to fit, and converts audio into
the format the bar expects. (`storage_write`, further down, applies the same
conversion automatically — `assets_upload` is the lower-level path.)

Now show it on the back display:

```python
bb.display_draw(
    types.DisplayElements(
        application_name="my-app",
        elements=[
            types.ImageElement(
                id="icon",
                type="image",
                x=0,
                y=0,
                path="icon.png",
                display=types.DisplayName.BACK,
            ),
        ],
    )
)
```

### 3.3 Play a sound

Upload the audio the same way, then play it:

```python
with open("alert.wav", "rb") as f:
    filename, payload = converter.convert_for_storage("alert.wav", f.read())

bb.assets_upload(application_name="my-app", filename=filename, data=payload)
bb.audio_play(application_name="my-app", path=filename)
```

Stop playback with `bb.audio_stop()`.

### 3.4 Clean up

```python
bb.display_clear()
bb.assets_delete(application_name="my-app")
```

### 3.5 The whole thing

```python
from busylib import BusyBar, converter, types

APP = "my-app"


def upload(bb: BusyBar, path: str) -> str:
    """Convert a local file for the device and upload it."""
    with open(path, "rb") as handle:
        filename, payload = converter.convert_for_storage(path, handle.read())
    bb.assets_upload(application_name=APP, filename=filename, data=payload)
    return filename


def main() -> None:
    with BusyBar("10.0.4.20") as bb:
        print(f"Connected to firmware {bb.version().version}")

        icon = upload(bb, "icon.png")
        alert = upload(bb, "alert.wav")

        bb.display_draw(
            types.DisplayElements(
                application_name=APP,
                elements=[
                    types.TextElement(
                        id="status",
                        type="text",
                        x=2,
                        y=4,
                        text="BUILDING",
                        font="small",
                        display=types.DisplayName.FRONT,
                    ),
                    types.ImageElement(
                        id="icon",
                        type="image",
                        x=0,
                        y=0,
                        path=icon,
                        display=types.DisplayName.BACK,
                    ),
                ],
            )
        )
        bb.audio_play(application_name=APP, path=alert)


if __name__ == "__main__":
    main()
```

### Try the interactive example

`examples/remote` mirrors both displays in your terminal, forwards key presses
to the bar, and has commands for drawing text, playing audio, renaming the
device, and running setup:

```bash
uv run python -m examples.remote.main 10.0.4.20
```

## Going further

Client method names follow BUSY Bar API path segments instead of generic
`get_*`/`set_*` prefixes. For example, `/api/display/draw` maps to
`display_draw`, `/api/audio/play` maps to `audio_play`, and
`/api/storage/remove` maps to `storage_remove`.

### Context manager and async

```python
from busylib import BusyBar

with BusyBar("10.0.4.20") as bb:
    print(bb.version().version)
```

For concurrent workflows, use the async client to avoid blocking I/O:

```python
import asyncio

from busylib import AsyncBusyBar


async def main() -> None:
    async with AsyncBusyBar("10.0.4.20") as bb:
        version_info = await bb.version()
        print(f"Device version: {version_info.version}")


if __name__ == "__main__":
    asyncio.run(main())
```

### Reading device status

```python
version = bb.version()
print(f"Version: {version.version}, Branch: {version.branch}")

status = bb.status()
if status.system:
    print(f"Uptime: {status.system.uptime}")
if status.power:
    print(f"Battery: {status.power.battery_charge}%")

brightness = bb.display_brightness()
print(f"Front brightness: {brightness.front}, Back brightness: {brightness.back}")

volume = bb.audio_volume()
print(f"Volume: {volume.volume}")
```

### Discovering devices on the network

Instead of hardcoding an IP address, you can discover devices like so:

```python
from busylib import BusyBarDevices

for device in BusyBarDevices.discover():
    print(f"Device: {device.name}")
    print(f"  Over USB: {device.get_address('over_usb')}")
    print(f"  Over Wi-Fi: {device.get_address('over_wifi')}")

# Example output:
# Device: "Anna's BUSY Bar"
#   Over USB: 10.0.4.20
#   Over Wi-Fi: 192.168.100.2
```

Both the `remote` and `setup` examples use this automatically when no address is
given: they discover devices via mDNS, let you pick one by name if more than one
is found, and prompt for the access key if the bar needs one. Shipped firmware
doesn't advertise the `_busybar._tcp` service yet, so if nothing is found they
fall back to the well-known USB address `10.0.4.20`.

### Working with storage

Unlike `assets_upload`, `storage_write` converts media for the device
automatically:

```python
file_data = b"Hello, world!"
response = bb.storage_write(path="/my-app/data.txt", data=file_data)

file_content = bb.storage_read(path="/my-app/data.txt")
print(file_content.decode('utf-8'))

storage_list = bb.storage_list(path="/my-app")
for item in storage_list.list:
    if item.type == "file":
        print(f"File: {item.name} ({item.size} bytes)")
    else:
        print(f"Directory: {item.name}")

response = bb.storage_mkdir(path="/my-app/subdirectory")

response = bb.storage_remove(path="/my-app/data.txt")
```

### Preparing and executing requests separately

You can prepare a low-level request first and execute it later, optionally
with a different HTTP client/pool.

```python
from busylib import BusyBar

bb = BusyBar("10.0.4.20")
prepared = bb.prepare_request(
    "POST",
    "/api/audio/play",
    json_payload={"application_name": "my-app", "path": "notification.snd"},
)

# execute now
result = bb.execute_prepared_request(prepared)

# or execute with an external client
# with httpx.Client(base_url="http://10.0.4.20") as ext:
#     result = bb.execute_prepared_request(prepared, client=ext)
```

## API compatibility

By default, `version()` records the device `api_semver` and logs a warning when
it does not match the library compatibility header — which is what you'll see on
a factory bar until you update it.

Strict mode turns that warning into an error, so an incompatible bar fails fast
instead of misbehaving later. It will raise on firmware 1.0.2, so use it once
your bar is updated:

```python
bb = BusyBar("10.0.4.20", compatibility_mode="strict")
bb.version()  # raises BusyBarAPIVersionError if the firmware is too old
```

For migrations and diagnostics, methods can expose the minimum firmware
OpenAPI version their current implementation targets (not necessarily the
version where the underlying device endpoint first appeared).

```python
metadata = bb.method_compatibility("log_dump")
# {"version": "25.0.0", "path": "/api/log_dump", "method": "POST"}
```

### Versioning policy

When a device endpoint's contract changes in a way that isn't translatable
(renamed/re-typed parameters, new validation, a different response shape),
`busylib` takes a clean break instead of carrying a silent compatibility
shim:

- The helper is rewritten against the new contract and its
  `@requires_openapi(...)` version is bumped to record what it now targets.
- The old parameter/behavior is removed, not aliased. A caller depending on
  the old contract gets a clear `TypeError`/`ValueError` at the call site
  instead of a confusing error from the device.
- Projects that must keep talking to older firmware should pin the
  `busylib` version that matches that firmware (see `AGENTS.md`: "upgrade or
  pin `busylib` intentionally instead of assuming latest methods exist"),
  rather than expecting a single library version to speak every firmware
  contract at once.

## Agent-assisted scripts

This repository includes
[`AGENTS.md`](https://github.com/busy-app/busylib-py/blob/main/AGENTS.md), a compact guide for coding
BUSY Bar scripts and small apps with AI coding agents. It covers how to inspect
the installed `busylib` API before coding, avoid invented methods or payloads,
reuse clients safely, keep device effects bounded, and structure non-trivial
scripts with dry-run support.

## Links

- Documentation: https://busy-app.github.io/busylib-py/
- Source: https://github.com/busy-app/busylib-py
- PyPI: https://pypi.org/project/busylib/

## Development

To set up a development environment, clone the repository and install the package in editable mode with test dependencies:

```bash
git clone https://github.com/busy-app/busylib-py
cd busylib-py
python3 -m venv .venv
source .venv/bin/activate
make install-dev
```
