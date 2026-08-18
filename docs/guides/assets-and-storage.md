# Assets and storage

There are two ways to put a file on a BUSY Bar, and the difference matters:

| Method | Path | Converts media? |
| --- | --- | --- |
| `assets_upload` | `/api/assets/upload` | **No** — bytes are sent as-is |
| `storage_write` | `/api/storage/write` | **Yes** — automatically |

`assets_upload` is the lower-level path. If you hand it a photo straight off
disk, that's exactly what lands on the device: wrong dimensions, wrong format,
nothing useful on screen. Convert first.

## Converting

```python
from busylib import converter

with open("icon.png", "rb") as handle:
    filename, payload = converter.convert_for_storage("icon.png", handle.read())

response = bb.assets_upload(application_name="my-app", filename=filename, data=payload)
print(filename, response.result)
```

**Example output for a PNG:**

```
icon.png OK
```

`icon.png` is the device-side filename after conversion, and `OK` confirms the
upload. Nothing appears on a display until you reference the asset in a draw
or playback call.

`convert_for_storage` dispatches on the file extension and returns a
`(path, data)` pair — the name can change if the target format differs.

Images are opened with Pillow, scaled and centre-cropped to the target display,
and re-encoded as PNG. Supported: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tif`,
`.tiff`, `.webp`. Animated images raise `NotImplementedError`.

Audio (`.mp3`, `.ogg`, `.aac`, `.m4a`, `.flac`, `.wav`) and video/GIF
(`.gif`, `.mov`, `.mp4`, `.mkv`, `.avi`, `.webm`) are converted to the formats
the bar plays and displays.

Unknown extensions pass through untouched, so plain data files are safe:

```python
response = bb.storage_write(path="/ext/my-app/data.txt", data=b"Hello, world!")
print(response.result)
```

**Expected output:**

```
OK
```

The file now exists at `/ext/my-app/data.txt`; media files passed to this method
are converted before they are written.

Storage paths have to start with `/ext`, the bar's user-writable area. A path
outside it is not answered at all — no error response — so the call ends in a
timeout after retries rather than telling you the path was wrong.

Anything that *is* recognised but fails to convert raises
`BusyBarConversionError` rather than silently uploading unusable bytes.

## Referencing uploaded files

An uploaded asset is addressed by its filename from within the same
`application_name`:

```python
bb.audio_play(application_name="my-app", path=filename)
```

…and the same name goes into an `ImageElement.path` when drawing.

**Expected result:** playback starts without terminal output. The filename is
looked up inside `my-app`, so the application name must match the upload.

## Cleaning up

```python
response = bb.assets_delete(application_name="my-app")
print(response.result)
```

**Expected output:**

```
OK
```

All assets belonging to `my-app` are removed; files in general storage and
assets belonging to other applications remain untouched.

Storage has the usual file operations — `storage_read`, `storage_list`,
`storage_mkdir`, `storage_remove` — all taking an absolute device path under
`/ext`.
