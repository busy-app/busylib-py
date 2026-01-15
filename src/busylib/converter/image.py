from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from .. import display

logger = logging.getLogger(__name__)


def _center_crop(image: Image.Image, width: int, height: int) -> Image.Image:
    """
    Crop the image around the center to the requested size.

    Returns the original image when the requested size is larger.
    """
    img_w, img_h = image.size
    if width > img_w or height > img_h:
        return image
    left = (img_w - width) // 2
    top = (img_h - height) // 2
    right = left + width
    bottom = top + height
    return image.crop((left, top, right, bottom))


def _resize_for_display(
    image: Image.Image,
    width: int,
    height: int,
    *,
    scale: bool,
    crop: bool,
) -> Image.Image:
    """
    Optionally scale and crop the image to fit the target size.

    Scaling uses a cover strategy to avoid letterboxing before crop.
    """
    img_w, img_h = image.size
    if scale and (img_w > width or img_h > height):
        scale_factor = max(width / img_w, height / img_h)
        new_size = (
            max(1, int(img_w * scale_factor)),
            max(1, int(img_h * scale_factor)),
        )
        resampling = getattr(Image, "Resampling", None)
        resample_filter = getattr(resampling, "LANCZOS", 3)
        image = image.resize(new_size, resample_filter)
    if crop:
        return _center_crop(image, width, height)
    return image


def convert(
    path: str,
    data: bytes,
    *,
    display_name: display.DisplayName | int | str = display.DisplayName.FRONT,
    scale: bool = True,
    crop: bool = True,
) -> tuple[str, bytes] | None:
    """
    Convert image bytes to a PNG suitable for the target display.

    Applies optional downscaling and center-crop to match the device size.
    """
    try:
        image = Image.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to open image: {exc}") from exc

    if getattr(image, "is_animated", False):
        raise NotImplementedError("Animated images are not supported yet")

    spec = display.get_display_spec(display_name)
    image = _resize_for_display(image, spec.width, spec.height, scale=scale, crop=crop)

    output = io.BytesIO()
    image.save(output, format="PNG")
    new_path = str(Path(path).with_suffix(".png"))
    logger.debug("Converted %s to PNG", path)
    return new_path, output.getvalue()
