# busylib

[![PyPI version](https://img.shields.io/pypi/v/busylib.svg?label=PyPI)](https://pypi.org/project/busylib/)
[![Python versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/busylib/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/busy-app/busylib-py/blob/main/LICENSE)

A simple and intuitive Python client for interacting with the Busy Bar API. This library allows you to programmatically control the device's display, audio, and assets.

## Features

-   Easy-to-use API for all major device functions.
-   Upload and manage assets for your applications.
-   Control the display by drawing text and images.
-   Play and stop audio files.
-   Built-in validation for device IP addresses.

## Installation

You can install `busylib` directly from PyPI:

```bash
pip install busylib
```

Upgrade to the latest release:

```bash
pip install --upgrade busylib
```

## Usage

First, import and initialize the `BusyBar` client with IP address of your device.

```python
from busylib import BusyBar

bb = BusyBar("10.0.4.20")

version_info = bb.version()
print(f"Device version: {version_info.version}")
```

You can also use context manager.

```python
from busylib import BusyBar

with BusyBar("10.0.4.20") as bb:
    version_info = bb.version()
    print(f"Device version: {version_info.version}")
```

For concurrent workflows, use the async client to avoid blocking I/O.

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

## API Compatibility

By default, `version()` records the device `api_semver` and logs a warning when
it does not match the library compatibility header. Use strict mode when your
application should fail fast on incompatible firmware.

```python
bb = BusyBar("10.0.4.20", compatibility_mode="strict")
bb.version()
```

For migrations and diagnostics, methods can expose the OpenAPI version where
they were introduced.

```python
metadata = bb.method_compatibility("log_dump")
# {"version": "25.0.0", "path": "/api/log_dump", "method": "POST"}
```

## Agent-Assisted Scripts

This repository includes [`AGENTS.md`](AGENTS.md), a compact guide for coding
Busy Bar scripts and small apps with AI coding agents. It covers how to inspect
the installed `busylib` API before coding, avoid invented methods or payloads,
reuse clients safely, keep device effects bounded, and structure non-trivial
scripts with dry-run support.

## API Examples

Here are some examples of how to use the library to control your Busy Bar device.

Client method names follow Busy Bar API path segments instead of generic
`get_*`/`set_*` prefixes. For example, `/api/display/draw` maps to
`display_draw`, `/api/audio/play` maps to `audio_play`, and
`/api/storage/remove` maps to `storage_remove`.

### Uploading an Asset

You can upload files (like images or sounds) to be used by your application on the device.

```python
with open("path/to/your/image.png", "rb") as f:
    file_bytes = f.read()
    response = bb.assets_upload(
        application_name="my-app",
        filename="logo.png",
        data=file_bytes,
    )
    print(f"Upload result: {response.result}")


with open("path/to/your/sound.wav", "rb") as f:
    file_bytes = f.read()
    response = bb.assets_upload(
        application_name="my-app",
        filename="notification.wav",
        data=file_bytes,
    )
```

### Drawing on the Display

Draw text or images on the device's screen. The `display_draw` method accepts a `DisplayElements` object containing a list of elements to render.

```python
from busylib import types


text_element = types.TextElement(
    id="hello",
    type="text",
    x=10,
    y=20,
    text="Hello, World!",
    font="small",
    display=types.DisplayName.FRONT,
)

image_element = types.ImageElement(
    id="logo",
    type="image",
    x=50,
    y=40,
    path="logo.png",
    display=types.DisplayName.BACK,
)

display_data = types.DisplayElements(
    application_name="my-app",
    elements=[text_element, image_element]
)

response = bb.display_draw(display_data)
print(f"Draw result: {response.result}")
```

### Clearing the Display

To clear everything from the screen:

```python
response = bb.display_clear()
print(f"Clear result: {response.result}")
```

### Playing Audio

Play an audio file that you have already uploaded.

```python
response = bb.audio_play(application_name="my-app", path="notification.wav")
print(f"Play result: {response.result}")
```

### Stopping Audio

To stop any audio that is currently playing:

```python
response = bb.audio_stop()
print(f"Stop result: {response.result}")
```

### Deleting All Assets for an App

This will remove all files associated with a specific `application_name`.

```python
response = bb.assets_delete(application_name="my-app")
print(f"Delete result: {response.result}")
```

### Getting Device Status

You can get various status information from the device:

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
# Device: "Anna's Busy Bar"
#   Over USB: 10.0.4.20
#   Over Wi-Fi: 192.168.100.2
```

### Preparing and Executing Requests Separately

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

### Working with Storage

You can manage files in the device's storage:

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

## Links

- Documentation: https://busylib.readthedocs.io
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

To run the tests:

```bash
make test
```

To regenerate protobuf models for `/api/status/ws`:

```bash
make proto-sync
```

This target pulls schemas from `https://github.com/flipperdevices/bsb-protobuf`
into `.cache/bsb-protobuf` and regenerates Python protobuf modules in
`src/busylib/state_stream_proto` using `uv run python -m grpc_tools.protoc`
from dev dependencies.
