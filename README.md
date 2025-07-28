# busylib

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

## Usage

First, import and initialize the `BusyBar` client with the IP address of your device.

```python
from busylib import BusyBar

try:
    # Default IP is 10.0.4.20, but you can specify your own
    bb = BusyBar("10.0.4.20")
except ValueError as e:
    print(f"Error: {e}")


# Now you can use the bb object to interact with your device.
bb.get_version()
```

```python
from busylib import BusyBar

with BusyBar("10.0.4.20") as bb:
    bb.get_version()
```

## API Examples

Here are some examples of how to use the library to control your Busy Bar device.

### Uploading an Asset

You can upload files (like images or sounds) to be used by your application on the device.

```python
# Upload a file from bytes
with open("path/to/your/image.png", "rb") as f:
    file_bytes = f.read()
    bb.upload_asset(
        app_id="my-app",
        file_name="logo.png",
        file=file_bytes
    )

# Or upload directly from a file-like object
with open("path/to/your/sound.wav", "rb") as f:
    bb.upload_asset(
        app_id="my-app",
        file_name="notification.wav",
        file=f
    )
```

### Drawing on the Display

Draw text or images on the device's screen. The `draw_display` method accepts a list of elements to render.

```python
elements = [
    {
        "id": "0",
        "type": "text",
        "text": "Hello, World!",
        "x": 0,
        "y": 2,
        "display": "front",
    },
    {
        "id": "1",
        "type": "image",
        "path": "logo.png", # Must be uploaded first
        "x": 50,
        "y": 40,
        "display": "back",

    }
]

bb.draw_display(app_id="my-app", elements=elements)
```

### Clearing the Display

To clear everything from the screen:

```python
bb.clear_display()
```

### Playing a Sound

Play an audio file that you have already uploaded.

```python
bb.play_sound(app_id="my-app", path="notification.wav")
```

### Stopping a Sound

To stop any audio that is currently playing:

```python
bb.stop_sound()
```

### Deleting All Assets for an App

This will remove all files associated with a specific `app_id`.

```python
bb.delete_assets(app_id="my-app")
```

## Development

To set up a development environment, clone the repository and install the package in editable mode with test dependencies:

```bash
git clone https://github.com/busy-app/busylib
cd busylib
python3 -m venv .venv
source .venv/bin/activate
make install-dev
```

To run the tests:

```bash
make test
```
