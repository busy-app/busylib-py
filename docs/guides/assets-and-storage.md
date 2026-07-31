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

bb.assets_upload(application_name="my-app", filename=filename, data=payload)
```

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
bb.storage_write(path="/my-app/data.txt", data=b"Hello, world!")
```

Anything that *is* recognised but fails to convert raises
`BusyBarConversionError` rather than silently uploading unusable bytes.

## Referencing uploaded files

An uploaded asset is addressed by its filename from within the same
`application_name`:

```python
bb.audio_play(application_name="my-app", path=filename)
```

…and the same name goes into an `ImageElement.path` when drawing.

## Cleaning up

```python
bb.assets_delete(application_name="my-app")
```

Storage has the usual file operations — `storage_read`, `storage_list`,
`storage_mkdir`, `storage_remove` — all taking an absolute device path.
