# busylib

[![PyPI](https://img.shields.io/pypi/v/busylib.svg)](https://pypi.org/project/busylib/)
[![Python Versions](https://img.shields.io/pypi/pyversions/busylib.svg)](https://pypi.org/project/busylib/)
[![License](https://img.shields.io/pypi/l/busylib.svg)](https://github.com/busy-app/busylib-py/blob/main/LICENSE)

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

version_info = bb.get_version()
print(f"Device version: {version_info.version}")
```

You can also use context manager.

```python
from busylib import BusyBar

with BusyBar("10.0.4.20") as bb:
    version_info = bb.get_version()
    print(f"Device version: {version_info.version}")
```

For concurrent workflows, use the async client to avoid blocking I/O.

```python
import asyncio

from busylib import AsyncBusyBar


async def main() -> None:
    async with AsyncBusyBar("10.0.4.20") as bb:
        version_info = await bb.get_version()
        print(f"Device version: {version_info.version}")


if __name__ == "__main__":
    asyncio.run(main())
```

## API Examples

Here are some examples of how to use the library to control your Busy Bar device.

### Uploading an Asset

You can upload files (like images or sounds) to be used by your application on the device.

```python
with open("path/to/your/image.png", "rb") as f:
    file_bytes = f.read()
    response = bb.upload_asset(
        app_id="my-app",
        filename="logo.png",
        data=file_bytes,
    )
    print(f"Upload result: {response.result}")


with open("path/to/your/sound.wav", "rb") as f:
    file_bytes = f.read()
    response = bb.upload_asset(
        app_id="my-app",
        filename="notification.wav",
        data=file_bytes,
    )
```

### Drawing on the Display

Draw text or images on the device's screen. The `draw_on_display` method accepts a `DisplayElements` object containing a list of elements to render.

```python
from busylib import types


text_element = types.TextElement(
    id="hello",
    type="text",
    x=10,
    y=20,
    text="Hello, World!",
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
    app_id="my-app",
    elements=[text_element, image_element]
)

response = bb.draw_on_display(display_data)
print(f"Draw result: {response.result}")
```

### Clearing the Display

To clear everything from the screen:

```python
response = bb.clear_display()
print(f"Clear result: {response.result}")
```

### Playing Audio

Play an audio file that you have already uploaded.

```python
response = bb.play_audio(app_id="my-app", path="notification.wav")
print(f"Play result: {response.result}")
```

### Stopping Audio

To stop any audio that is currently playing:

```python
response = bb.stop_audio()
print(f"Stop result: {response.result}")
```

### Deleting All Assets for an App

This will remove all files associated with a specific `app_id`.

```python
response = bb.delete_app_assets(app_id="my-app")
print(f"Delete result: {response.result}")
```

### Getting Device Status

You can get various status information from the device:

```python
version = bb.get_version()
print(f"Version: {version.version}, Branch: {version.branch}")

status = bb.get_status()
if status.system:
    print(f"Uptime: {status.system.uptime}")
if status.power:
    print(f"Battery: {status.power.battery_charge}%")

brightness = bb.get_display_brightness()
print(f"Front brightness: {brightness.front}, Back brightness: {brightness.back}")

volume = bb.get_audio_volume()
print(f"Volume: {volume.volume}")
```

### Working with Storage

You can manage files in the device's storage:

```python
file_data = b"Hello, world!"
response = bb.write_storage_file(path="/my-app/data.txt", data=file_data)

file_content = bb.read_storage_file(path="/my-app/data.txt")
print(file_content.decode('utf-8'))

storage_list = bb.list_storage_files(path="/my-app")
for item in storage_list.list:
    if item.type == "file":
        print(f"File: {item.name} ({item.size} bytes)")
    else:
        print(f"Directory: {item.name}")

response = bb.create_storage_directory(path="/my-app/subdirectory")

response = bb.remove_storage_file(path="/my-app/data.txt")
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
