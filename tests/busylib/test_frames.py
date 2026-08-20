"""
The frame object: geometry, pixel access, and encoding without Pillow.
"""

from __future__ import annotations

import base64
import zlib

import pytest

from busylib import display
from busylib.frames import Frame

FRONT = display.get_display_spec(0)


def _solid(colour: tuple[int, int, int], spec=FRONT) -> bytes:
    return bytes(colour) * (spec.width * spec.height)


def test_geometry_comes_from_the_display() -> None:
    """
    A frame knows its own size, so callers stop passing it around.
    """
    frame = Frame.from_screen(_solid((1, 2, 3)), 0)

    assert (frame.width, frame.height) == (FRONT.width, FRONT.height)
    assert frame.display.name is display.DisplayName.FRONT


def test_wrong_length_is_rejected_on_construction() -> None:
    """
    A short buffer fails immediately rather than reading past a row later.
    """
    with pytest.raises(ValueError, match="needs 3456 bytes"):
        Frame.from_screen(b"\x01\x02\x03", 0)


def test_pixel_reads_by_coordinate() -> None:
    """
    Pixels are addressed by x and y instead of a computed offset.
    """
    data = bytearray(_solid((0, 0, 0)))
    offset = (3 * FRONT.width + 5) * 3
    data[offset : offset + 3] = bytes((10, 20, 30))

    frame = Frame.from_screen(bytes(data), 0)

    assert frame.pixel(5, 3) == (10, 20, 30)
    assert frame.pixel(0, 0) == (0, 0, 0)


@pytest.mark.parametrize("x,y", [(-1, 0), (0, -1), (72, 0), (0, 16)])
def test_pixel_outside_the_display_raises(x: int, y: int) -> None:
    """
    Off-display coordinates raise instead of returning a neighbouring row.
    """
    frame = Frame.from_screen(_solid((0, 0, 0)), 0)

    with pytest.raises(IndexError):
        frame.pixel(x, y)


def test_rows_and_pixels_agree() -> None:
    """
    Both views describe the same buffer.
    """
    frame = Frame.from_screen(_solid((7, 8, 9)), 0)

    rows = frame.rows()
    assert len(rows) == FRONT.height
    assert all(len(row) == FRONT.width * 3 for row in rows)
    assert len(frame.pixels()) == FRONT.width * FRONT.height
    assert frame.pixels()[0] == (7, 8, 9)


def test_is_blank() -> None:
    """
    A dark screen is reported as blank.
    """
    assert Frame.from_screen(_solid((0, 0, 0)), 0).is_blank()
    assert not Frame.from_screen(_solid((0, 0, 1)), 0).is_blank()


def test_to_png_is_a_real_png() -> None:
    """
    The encoder is hand-written on zlib, so check its structure.

    Signature, an IHDR describing the frame, and an IEND terminator - enough
    that a decoder will accept it, without needing an imaging library here.
    """
    frame = Frame.from_screen(_solid((255, 0, 0)), 0)

    png = frame.to_png()

    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert png[12:16] == b"IHDR"
    width, height, depth, colour_type = (
        int.from_bytes(png[16:20], "big"),
        int.from_bytes(png[20:24], "big"),
        png[24],
        png[25],
    )
    assert (width, height) == (FRONT.width, FRONT.height)
    assert (depth, colour_type) == (8, 2), "8-bit truecolour"
    assert png[-8:-4] == b"IEND"


def test_png_pixels_survive_a_round_trip() -> None:
    """
    Decode the PNG back by hand and compare with the source bytes.
    """
    data = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255]) * (FRONT.width * FRONT.height // 3)
    png = Frame.from_screen(data, 0).to_png()

    # Walk the chunks to find IDAT, then inflate and strip the per-row filter.
    offset, payload = 8, b""
    while offset < len(png):
        length = int.from_bytes(png[offset : offset + 4], "big")
        kind = png[offset + 4 : offset + 8]
        if kind == b"IDAT":
            payload += png[offset + 8 : offset + 8 + length]
        offset += 12 + length

    raw = zlib.decompress(payload)
    stride = FRONT.width * 3
    rows = [
        raw[i + 1 : i + 1 + stride]  # drop the filter byte
        for i in range(0, len(raw), stride + 1)
    ]
    assert b"".join(rows) == data


def test_from_state_update_fills_in_omitted_defaults() -> None:
    """
    A plain RGB frame arrives with neither `encoding` nor `pixel_format`.

    Protobuf omits fields holding a default value, so the absence means
    PLAIN/RGB888 rather than missing data. Reading it as missing is what makes
    `decode_frame_data` raise on a perfectly ordinary frame.
    """
    device_order = bytes([3, 2, 1]) * (FRONT.width * FRONT.height)
    update = {"data": base64.b64encode(device_order).decode(), "screen": "FRONT"}

    frame = Frame.from_state_update(update)

    assert frame.pixel(0, 0) == (1, 2, 3)


def test_from_state_update_handles_compression() -> None:
    """
    A DEFLATE frame is inflated on the way in.
    """
    device_order = bytes([9, 8, 7]) * (FRONT.width * FRONT.height)
    update = {
        "data": base64.b64encode(zlib.compress(device_order)).decode(),
        "encoding": "DEFLATE",
        "pixel_format": "RGB888",
        "screen": "FRONT",
    }

    assert Frame.from_state_update(update).pixel(0, 0) == (7, 8, 9)


def test_from_state_update_without_data_is_rejected() -> None:
    """
    An update carrying no frame bytes is an error, not an empty frame.
    """
    with pytest.raises(ValueError, match="no data"):
        Frame.from_state_update({"screen": "FRONT"})


def test_to_pillow_matches_the_buffer() -> None:
    """
    The optional Pillow view holds the same pixels.

    Pillow is imported lazily, so everything above works without it.
    """
    pytest.importorskip("PIL")
    data = _solid((4, 5, 6))

    image = Frame.from_screen(data, 0).to_pillow()

    assert image.mode == "RGB"
    assert image.size == (FRONT.width, FRONT.height)
    assert image.tobytes() == data


def test_frames_module_does_not_import_pillow() -> None:
    """
    Importing the module must not pull in a 13 MB imaging library.
    """
    import subprocess
    import sys

    code = (
        "import sys; import busylib.frames; "
        "print('PIL' in sys.modules or 'PIL.Image' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "False", result.stdout


def test_the_wire_format_name_is_accepted_and_translated() -> None:
    """
    Both the device's name and this package's name decode identically.

    The firmware calls its colour format RGB888 while sending blue first, so
    the name is translated at the edge. It still has to be accepted: it is
    what arrives on real frames.
    """
    from busylib import display

    device_order = bytes([3, 2, 1])

    assert display.WIRE_PIXEL_FORMATS["RGB888"] == display.COLOUR_FORMAT
    assert display.decode_frame_data(
        "PLAIN", "RGB888", device_order
    ) == display.decode_frame_data("PLAIN", display.COLOUR_FORMAT, device_order)
    assert display.decode_frame_data("PLAIN", "RGB888", device_order) == bytes(
        [1, 2, 3]
    )
