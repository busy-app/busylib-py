# Displays and frames

## Frames

`frame()` returns what is on a display as a `Frame`: the pixels, their
geometry, and which display they came from, kept together.

```python
from busylib import BusyBar

with BusyBar("10.0.4.20") as bb:
    front = bb.frame(0)

    print(front.width, front.height)  # 72 16
    print(front.pixel(2, 8))  # (255, 0, 0)
    open("front.png", "wb").write(front.to_png())
```

`screen()` is still there and still returns the raw bytes, for anyone feeding
them somewhere that wants a flat buffer.

Two things `Frame` settles that a bare buffer leaves to the caller. The bytes
are **RGB**: the device orders colour as BGR, and that is undone before you
see it. And `to_png()` uses only the standard library, so writing a frame to a
file or a web page needs nothing installed — Pillow is optional and imported
only if you ask for `to_pillow()`.

The front display is 72x16, and most viewers draw that as a postage stamp or
smooth it into mush. `scale()` enlarges a frame by repeating whole pixels, so
it stays square and legible at any size:

```python
open("front.png", "wb").write(front.scale(10).to_png())  # 720x160
```

The enlarged frame still names the screen it came from, and says so in its
description; only its geometry changes.

Anything that shows a picture in a fixed shape - a square tile, a round
thumbnail - crops a 72x16 strip to nothing. `pad()` centres the frame in a
larger one instead, so the whole display survives:

```python
big = front.scale(8)
square = big.pad(big.width, big.width)  # 576x576, the strip in the middle
```

The fill is black by default, which is what an unlit panel looks like, so the
result reads as the strip with the rest of the bar around it.

Frames also arrive on the status stream, where they are compressed and
described by their own metadata:

```python
async for state in bb.stream_status_ws():
    for update in state.get("updates", []):
        if "frame" in update:
            frame = Frame.from_state_update(update["frame"])
```

`from_state_update` fills in the metadata protobuf leaves out. A plain
uncompressed RGB frame arrives with neither `encoding` nor `pixel_format`,
because both hold their enum's first value — reading that absence as missing
data is the mistake it exists to prevent.

::: busylib.frames

## Display specifications

Helpers describing the two physical displays and decoding the frame data the
device sends back.

::: busylib.display
