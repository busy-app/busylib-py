from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import TypeAlias

from .types import DisplayName

# Pixel formats, named for what the bytes are. The firmware's protobuf calls
# its colour format RGB888, but the bytes arrive blue first: drawing #FF0000
# reads back as (0, 0, 255), over both the HTTP frame and the state stream.
# Repeating the firmware's name inside this package taught every reader the
# wrong thing, so it is translated at the edge and never used past it. The
# integration suite draws a colour and reads it back, which re-checks this
# against whatever firmware is actually in front of you.
COLOUR_FORMAT = "BGR888"
GREY8_FORMAT = "L8"
GREY4_FORMAT = "L4"

# What the device puts on the wire, mapped to what this package calls it.
WIRE_PIXEL_FORMATS = {
    "RGB888": COLOUR_FORMAT,
    "L8": GREY8_FORMAT,
    "L4": GREY4_FORMAT,
}

# proto3 leaves out a field holding its enum's first value, so a frame with no
# pixel_format is a colour frame rather than one missing its format.
DEFAULT_PIXEL_FORMAT = COLOUR_FORMAT

# Block size the RLE codec compares for repeats, per pixel format. This is
# NOT bytes-per-pixel: it mirrors the firmware's screen streamer, which uses
# `blk_size = display_id == Front ? 3 : 2` in
# applications/services/state_publisher/screen_streamer.c - so L4 (the back
# display, 2 pixels packed per byte) is compared in 2-byte blocks.
_RLE_BLOCK_SIZE = {
    COLOUR_FORMAT: 3,
    GREY8_FORMAT: 1,
    GREY4_FORMAT: 2,
}


@dataclass(frozen=True)
class DisplaySpec:
    name: DisplayName
    index: int
    width: int
    height: int
    description: str


FRONT_DISPLAY = DisplaySpec(
    name=DisplayName.FRONT,
    index=0,
    width=72,
    height=16,
    description="72x16 RGB LED matrix, ~16M colors, >800 nits",
)

BACK_DISPLAY = DisplaySpec(
    name=DisplayName.BACK,
    index=1,
    width=160,
    height=80,
    description="160x80 monochrome OLED, 16 gray scales",
)


_DISPLAY_BY_NAME = {
    DisplayName.FRONT: FRONT_DISPLAY,
    DisplayName.BACK: BACK_DISPLAY,
}

_DISPLAY_BY_INDEX = {
    0: FRONT_DISPLAY,
    1: BACK_DISPLAY,
}


# What callers may pass anywhere a display is selected. `get_display_spec`
# accepts all of these, so endpoint methods advertise the same contract
# instead of narrowing to `int`.
DisplaySpecLike: TypeAlias = "DisplaySpec | DisplayName | int | str | None"


def get_display_spec(
    display: DisplaySpecLike,
) -> DisplaySpec:
    """
    Resolve a display spec using explicit front/back selection.

    `front` is used only when display is None. Any unsupported display value
    raises ValueError to avoid silently rendering to the wrong screen.
    """
    if isinstance(display, DisplaySpec):
        return display
    if display is None:
        return FRONT_DISPLAY
    if isinstance(display, DisplayName):
        return _DISPLAY_BY_NAME[display]
    if isinstance(display, int):
        if display in _DISPLAY_BY_INDEX:
            return _DISPLAY_BY_INDEX[display]
        raise ValueError(f"Unsupported display index: {display}")
    if isinstance(display, str):
        display_lower = display.strip().lower()
        for name, spec in _DISPLAY_BY_NAME.items():
            if name.value == display_lower:
                return spec
        raise ValueError(f"Unsupported display name: {display}")
    raise ValueError(f"Unsupported display value type: {type(display).__name__}")


def rle_decode(data: bytes, block_size: int) -> bytes | None:
    """
    Decode the run-length encoding used by `BSB_Frame.Frame.encoding`.

    A control byte with the high bit set is a literal run of
    `(ctrl & 0x7F) * block_size` raw bytes; otherwise it is a repeat count for
    the single block that follows. Returns None on truncated/malformed input.
    """
    out = bytearray()
    i = 0
    total = len(data)
    while i < total:
        ctrl = data[i]
        i += 1
        if ctrl & 0x80:
            count = ctrl & 0x7F
            need = count * block_size
            if i + need > total:
                return None
            out.extend(data[i : i + need])
            i += need
        else:
            count = ctrl
            if i + block_size > total:
                return None
            block = data[i : i + block_size]
            i += block_size
            out.extend(block * count)
    return bytes(out)


def unpack_l4_to_l8(data: bytes) -> bytes:
    """
    Expand packed 4-bit grayscale samples (two per byte) into one byte each.
    """
    out = bytearray(len(data) * 2)
    idx = 0
    for byte in data:
        out[idx] = byte & 0x0F
        out[idx + 1] = (byte >> 4) & 0x0F
        idx += 2
    return bytes(out)


def decode_frame_data(encoding: str, pixel_format: str, data: bytes) -> bytes:
    """
    Decode `BSB_Frame.Frame.data` into RGB bytes using its own metadata.

    `encoding` is the enum name the protobuf message reports
    (`PLAIN`/`RUN_LENGTH`/`DEFLATE`/`DEFLATE_RUN_LENGTH`). `pixel_format`
    accepts either the name the device sends or this package's own
    (`BGR888`/`L8`/`L4`), so callers can pass a frame's metadata straight
    through. Either way the result is RGB, three bytes per pixel.
    """
    normalized = WIRE_PIXEL_FORMATS.get(pixel_format, pixel_format)
    block_size = _RLE_BLOCK_SIZE.get(normalized)
    if block_size is None:
        raise ValueError(f"Unsupported frame pixel_format: {pixel_format}")

    if encoding in ("DEFLATE", "DEFLATE_RUN_LENGTH"):
        data = zlib.decompress(data)
    elif encoding not in ("PLAIN", "RUN_LENGTH"):
        raise ValueError(f"Unsupported frame encoding: {encoding}")

    if encoding in ("RUN_LENGTH", "DEFLATE_RUN_LENGTH"):
        decoded = rle_decode(data, block_size)
        if decoded is None:
            raise ValueError("Failed to RLE-decode frame data")
        data = decoded

    if normalized == COLOUR_FORMAT:
        # Blue and red change places on the way out. See COLOUR_FORMAT above
        # for why the format is not called RGB888 here.
        pixels = bytearray(data)
        pixels[0::3], pixels[2::3] = pixels[2::3], pixels[0::3]
        return bytes(pixels)
    if normalized == GREY8_FORMAT:
        return b"".join(bytes((v, v, v)) for v in data)
    unpacked = unpack_l4_to_l8(data)
    return b"".join(bytes((v * 17, v * 17, v * 17)) for v in unpacked)
