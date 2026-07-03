from __future__ import annotations

from collections.abc import Sequence

from pydantic_extra_types.color import Color


ColorInput = str | Sequence[int | float]


def normalize_rgba_color(value: ColorInput | None) -> str | None:
    """
    Normalize supported CSS-like and RGB/RGBA inputs to OpenAPI #RRGGBBAA.

    Integer channels are interpreted as 0-255 values, while float channels in
    the 0-1 range are scaled to 0-255 for common normalized RGBA inputs.
    """
    if value is None:
        return None

    if isinstance(value, (list, tuple)):
        if len(value) not in (3, 4):
            raise ValueError("Color tuple/list must have 3 (RGB) or 4 (RGBA) elements")

        def to_channel(component: int | float) -> int:
            if isinstance(component, float):
                scaled = component * 255 if component <= 1 else component
                return int(round(scaled))
            return int(component)

        r, g, b = [max(0, min(255, to_channel(c))) for c in value[:3]]
        alpha_component = value[3] if len(value) == 4 else 255
        alpha = max(0, min(255, to_channel(alpha_component)))
        return f"#{r:02X}{g:02X}{b:02X}{alpha:02X}"

    if not isinstance(value, str):
        raise ValueError("Color must be a string or RGB/RGBA tuple")

    col = Color(value)
    hex_value = col.as_hex().upper()
    if len(hex_value) == 9:
        return hex_value
    if len(hex_value) == 7:
        return f"{hex_value}FF"

    rgb = col.as_rgb_tuple()
    r, g, b = rgb[0], rgb[1], rgb[2]
    return f"#{r:02X}{g:02X}{b:02X}FF"
