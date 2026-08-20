from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import TypeAlias

from .types import DisplayName

# Block size the RLE codec compares for repeats, per pixel format. This is
# NOT bytes-per-pixel: it mirrors the firmware's screen streamer, which uses
# `blk_size = display_id == Front ? 3 : 2` in
# applications/services/state_publisher/screen_streamer.c - so L4 (the back
# display, 2 pixels packed per byte) is compared in 2-byte blocks.
_RLE_BLOCK_SIZE = {
    "RGB888": 3,
    "L8": 1,
    "L4": 2,
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

    `encoding` and `pixel_format` are the enum names as reported by the
    protobuf message (`PLAIN`/`RUN_LENGTH`/`DEFLATE`/`DEFLATE_RUN_LENGTH` and
    `RGB888`/`L8`/`L4`), so no guessing based on frame byte length is needed.
    """
    block_size = _RLE_BLOCK_SIZE.get(pixel_format)
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

    if pixel_format == "RGB888":
        # The enum says RGB888 and the device sends BGR: drawing #FF0000 comes
        # back as (0, 0, 255) on both the HTTP frame and the state stream,
        # verified against firmware 1.1.1. The name comes from the firmware's
        # own protobuf, so it cannot be trusted over the bytes.
        pixels = bytearray(data)
        pixels[0::3], pixels[2::3] = pixels[2::3], pixels[0::3]
        return bytes(pixels)
    if pixel_format == "L8":
        return b"".join(bytes((v, v, v)) for v in data)
    # L4
    unpacked = unpack_l4_to_l8(data)
    return b"".join(bytes((v * 17, v * 17, v * 17)) for v in unpacked)
