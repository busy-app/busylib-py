"""
A frame of pixels, and the few things people actually do with one.

The device hands out screen contents as a flat run of bytes, which is awkward
to work with and easy to misread - the byte order, the geometry and which
display it came from all have to be carried alongside by hand. `Frame` keeps
them together and answers the usual questions directly.

Nothing here needs a third-party package. PNG encoding uses `zlib` from the
standard library, and `to_pillow` imports Pillow only if you call it.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .display import (
    DEFAULT_PIXEL_FORMAT,
    DisplaySpec,
    DisplaySpecLike,
    decode_frame_data,
    get_display_spec,
)

if TYPE_CHECKING:  # pragma: no cover - import for type checkers only
    from PIL import Image

BYTES_PER_PIXEL = 3


@dataclass(frozen=True)
class Frame:
    """
    One screen's worth of pixels, as RGB bytes with their geometry attached.

    `data` holds three bytes per pixel in RGB order, row by row from the top
    left. The device sends colour as BGR; that is already undone here, so the
    bytes are ready to hand to anything that draws.
    """

    data: bytes
    display: DisplaySpec

    def __post_init__(self) -> None:
        expected = self.width * self.height * BYTES_PER_PIXEL
        if len(self.data) != expected:
            raise ValueError(
                f"{self.display.name.value} frame needs {expected} bytes "
                f"({self.width}x{self.height} RGB), got {len(self.data)}"
            )

    @property
    def width(self) -> int:
        """
        Pixels across, taken from the display this frame came from.
        """
        return self.display.width

    @property
    def height(self) -> int:
        """
        Pixels down, taken from the display this frame came from.
        """
        return self.display.height

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        """
        Return the RGB triple at `x`, `y`, counting from the top left.

        Raises `IndexError` outside the display, rather than reading a
        neighbouring row - a flat buffer makes that mistake silent.
        """
        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise IndexError(
                f"({x}, {y}) is outside the {self.width}x{self.height} display"
            )
        offset = (y * self.width + x) * BYTES_PER_PIXEL
        red, green, blue = self.data[offset : offset + BYTES_PER_PIXEL]
        return red, green, blue

    def rows(self) -> list[bytes]:
        """
        Split the frame into one bytes object per row of pixels.
        """
        stride = self.width * BYTES_PER_PIXEL
        return [self.data[i : i + stride] for i in range(0, len(self.data), stride)]

    def pixels(self) -> list[tuple[int, int, int]]:
        """
        Every pixel as an RGB triple, in reading order.
        """
        return [
            (self.data[i], self.data[i + 1], self.data[i + 2])
            for i in range(0, len(self.data), BYTES_PER_PIXEL)
        ]

    def is_blank(self) -> bool:
        """
        Whether every pixel is black.
        """
        return not any(self.data)

    def to_png(self) -> bytes:
        """
        Encode the frame as a PNG, using only the standard library.

        Enough to write the frame to a file or drop it into a web page, which
        is most of what people want from a frame, without asking anyone to
        install an imaging library for it.
        """
        stride = self.width * BYTES_PER_PIXEL
        # Each scanline is prefixed with its filter type; 0 means "store as
        # is", which keeps this simple and costs a little size.
        raw = b"".join(
            b"\x00" + self.data[i : i + stride]
            for i in range(0, len(self.data), stride)
        )

        def chunk(kind: bytes, payload: bytes) -> bytes:
            body = kind + payload
            return (
                struct.pack(">I", len(payload))
                + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
            )

        header = struct.pack(
            ">IIBBBBB",
            self.width,
            self.height,
            8,  # bits per channel
            2,  # colour type 2: truecolour, no alpha
            0,  # deflate
            0,  # adaptive filtering
            0,  # no interlacing
        )
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )

    def to_pillow(self) -> Image.Image:
        """
        Return the frame as a Pillow image, for scaling or further drawing.

        Pillow is imported here rather than at module load, so a frame can be
        read, inspected and saved as PNG without it installed.
        """
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "to_pillow needs Pillow installed; to_png needs nothing"
            ) from exc
        return Image.frombytes("RGB", (self.width, self.height), self.data)

    @classmethod
    def from_screen(cls, data: bytes, display: DisplaySpecLike) -> Frame:
        """
        Wrap already-decoded bytes, as returned by `screen()`.
        """
        return cls(data=data, display=get_display_spec(display))

    @classmethod
    def from_state_update(cls, frame_update: dict[str, Any]) -> Frame:
        """
        Build a frame from a `frame` update on the status stream.

        The stream compresses frames and describes them with its own metadata,
        and protobuf omits any field holding a default value - so a colour
        frame arrives with no `pixel_format` and an uncompressed one with no
        `encoding`. Both defaults are filled in here, because reading their
        absence as missing data is the mistake this method exists to prevent.
        """
        payload = frame_update.get("data")
        if payload is None:
            raise ValueError("frame update carries no data")
        if isinstance(payload, str):
            import base64

            payload = base64.b64decode(payload)

        decoded = decode_frame_data(
            frame_update.get("encoding") or "PLAIN",
            frame_update.get("pixel_format") or DEFAULT_PIXEL_FORMAT,
            bytes(payload),
        )
        screen = frame_update.get("screen") or "FRONT"
        return cls(data=decoded, display=get_display_spec(screen.lower()))
