from __future__ import annotations

import io

import pytest
from PIL import Image

from busylib import display
from busylib.converter import image as image_converter


def _make_image_bytes(size: tuple[int, int]) -> bytes:
    """
    Create a small JPEG image of the given size and return its bytes.
    """
    image = Image.new("RGB", size, color=(255, 0, 0))
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def test_image_convert_scales_and_crops_by_default() -> None:
    """
    Ensure image conversion produces PNG sized to front display by default.
    """
    spec = display.get_display_spec(display.DisplayName.FRONT)
    data = _make_image_bytes((300, 200))
    result = image_converter.convert("demo.jpg", data)
    assert result is not None
    new_path, payload = result
    assert new_path.endswith(".png")
    image = Image.open(io.BytesIO(payload))
    assert image.size == (spec.width, spec.height)


def test_image_convert_can_disable_scale_and_crop() -> None:
    """
    Ensure env flags disable scaling and cropping to keep original size.
    """
    data = _make_image_bytes((12, 8))
    result = image_converter.convert("demo.jpg", data, scale=False, crop=False)
    assert result is not None
    new_path, payload = result
    assert new_path.endswith(".png")
    image = Image.open(io.BytesIO(payload))
    assert image.size == (12, 8)


def test_image_convert_no_upscale_when_smaller() -> None:
    """
    Ensure smaller images are not upscaled by default.
    """
    data = _make_image_bytes((20, 10))
    result = image_converter.convert("demo.jpg", data)
    assert result is not None
    _new_path, payload = result
    image = Image.open(io.BytesIO(payload))
    assert image.size == (20, 10)


def test_image_convert_back_display_size() -> None:
    """
    Ensure conversion can target the back display size.
    """
    spec = display.get_display_spec(display.DisplayName.BACK)
    data = _make_image_bytes((400, 400))
    result = image_converter.convert(
        "demo.jpg", data, display_name=display.DisplayName.BACK
    )
    assert result is not None
    _new_path, payload = result
    image = Image.open(io.BytesIO(payload))
    assert image.size == (spec.width, spec.height)


def test_image_convert_rejects_animated_png() -> None:
    """
    Ensure animated PNGs are rejected as not implemented.
    """
    frames = [
        Image.new("RGB", (10, 10), color=(255, 0, 0)),
        Image.new("RGB", (10, 10), color=(0, 255, 0)),
    ]
    output = io.BytesIO()
    frames[0].save(
        output, format="PNG", save_all=True, append_images=frames[1:], loop=0
    )
    data = output.getvalue()
    with pytest.raises(NotImplementedError, match="Animated images"):
        image_converter.convert("demo.png", data)
