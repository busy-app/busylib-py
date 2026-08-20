from __future__ import annotations

import base64
import zlib

import pytest

from busylib import display
from busylib.features.dashboard import DeviceSnapshot, apply_state_stream_update

FRONT = display.get_display_spec(0)
BACK = display.get_display_spec(1)


def _frame_message(
    *,
    screen: str = "FRONT",
    encoding: str = "PLAIN",
    pixel_format: str = "RGB888",
    data: bytes = b"",
) -> dict[str, object]:
    """
    Build a state message carrying one `BSB_Frame.Frame` update.
    """
    return {
        "updates": [
            {
                "frame": {
                    "screen": screen,
                    "encoding": encoding,
                    "pixel_format": pixel_format,
                    "data": base64.b64encode(data).decode(),
                }
            }
        ]
    }


def test_plain_rgb_frame_lands_on_the_snapshot() -> None:
    """
    A well-formed front-display frame is decoded and stored as RGB.

    The device sends colour as BGR, so the snapshot holds the reordered
    bytes - what a renderer can use directly.
    """
    device_order = bytes([3, 2, 1]) * (FRONT.width * FRONT.height)
    snapshot = apply_state_stream_update(
        DeviceSnapshot(), _frame_message(data=device_order)
    )

    assert snapshot.screen_front is not None
    assert snapshot.screen_front.data == bytes([1, 2, 3]) * (FRONT.width * FRONT.height)
    assert snapshot.screen_front.pixel(0, 0) == (1, 2, 3)
    assert snapshot.screen_back is None


def test_l4_back_frame_is_expanded_to_rgb() -> None:
    """
    The back display's packed nibbles expand to RGB of the right size.
    """
    packed = bytes([0x21]) * ((BACK.width * BACK.height) // 2)
    message = _frame_message(screen="BACK", pixel_format="L4", data=packed)

    snapshot = apply_state_stream_update(DeviceSnapshot(), message)

    assert snapshot.screen_back is not None
    assert (snapshot.screen_back.width, snapshot.screen_back.height) == (
        BACK.width,
        BACK.height,
    )


def test_run_length_frame_is_decoded() -> None:
    """
    RUN_LENGTH frames are expanded before the size check.
    """
    pixels = FRONT.width * FRONT.height
    rle = bytes([9, 1, 2, 3]) * (pixels // 9)
    message = _frame_message(encoding="RUN_LENGTH", data=rle)

    snapshot = apply_state_stream_update(DeviceSnapshot(), message)

    assert snapshot.screen_front is not None
    assert len(snapshot.screen_front.data) == pixels * 3


def test_deflate_frame_is_decompressed() -> None:
    """
    DEFLATE frames inflate before being stored.
    """
    device_order = bytes([6, 5, 4]) * (FRONT.width * FRONT.height)
    message = _frame_message(encoding="DEFLATE", data=zlib.compress(device_order))

    snapshot = apply_state_stream_update(DeviceSnapshot(), message)

    assert snapshot.screen_front is not None
    assert snapshot.screen_front.data == bytes([4, 5, 6]) * (FRONT.width * FRONT.height)


def test_corrupt_deflate_frame_is_skipped_not_raised() -> None:
    """
    A corrupt DEFLATE payload must not escape the update handler.

    zlib.error derives from Exception rather than ValueError, so letting it
    through would kill the whole state-stream task over one bad frame.
    """
    message = _frame_message(encoding="DEFLATE", data=b"definitely-not-deflate")

    snapshot = apply_state_stream_update(DeviceSnapshot(), message)

    assert snapshot.screen_front is None


def test_frame_with_wrong_size_is_rejected() -> None:
    """
    A payload that doesn't match the display is dropped, not stored.

    An undersized frame would otherwise reach the renderer and fail there
    while unpacking pixel triples.
    """
    message = _frame_message(data=bytes([1, 2, 3]) * 10)

    snapshot = apply_state_stream_update(DeviceSnapshot(), message)

    assert snapshot.screen_front is None


def test_invalid_base64_is_skipped() -> None:
    """
    Non-base64 frame data is skipped rather than silently truncated.
    """
    message: dict[str, object] = {
        "updates": [
            {
                "frame": {
                    "screen": "FRONT",
                    "encoding": "PLAIN",
                    "pixel_format": "RGB888",
                    "data": "!!!! not base64 !!!!",
                }
            }
        ]
    }

    snapshot = apply_state_stream_update(DeviceSnapshot(), message)

    assert snapshot.screen_front is None


@pytest.mark.parametrize(
    "field,value",
    [("encoding", "LZMA"), ("pixel_format", "YUV420")],
)
def test_unsupported_frame_metadata_is_skipped(field: str, value: str) -> None:
    """
    Unknown encodings or pixel formats are skipped without raising.
    """
    payload = bytes([1, 2, 3]) * (FRONT.width * FRONT.height)
    message = _frame_message(data=payload)
    frame = message["updates"][0]["frame"]  # type: ignore[index]
    frame[field] = value  # type: ignore[index]

    snapshot = apply_state_stream_update(DeviceSnapshot(), message)

    assert snapshot.screen_front is None


def test_existing_frame_is_preserved_when_a_bad_one_arrives() -> None:
    """
    A bad frame must not wipe the last good one.
    """
    payload = bytes([7, 7, 7]) * (FRONT.width * FRONT.height)
    snapshot = apply_state_stream_update(DeviceSnapshot(), _frame_message(data=payload))

    snapshot = apply_state_stream_update(snapshot, _frame_message(data=b"\x01\x02"))

    assert snapshot.screen_front is not None
    assert snapshot.screen_front.data == payload
