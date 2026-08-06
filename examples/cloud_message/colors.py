from __future__ import annotations

# Kept as hex for readability; parse_color converts to RGBA channels.
NAMED_COLORS = {
    "amber": "FFBF00",
    "azure": "0080FF",
    "black": "000000",
    "blue": "0000FF",
    "cyan": "00FFFF",
    "gray": "808080",
    "green": "00FF00",
    "grey": "808080",
    "lime": "80FF00",
    "magenta": "FF00FF",
    "orange": "FF8000",
    "pink": "FF4080",
    "purple": "8000FF",
    "red": "FF0000",
    "teal": "00FF80",
    "violet": "8000FF",
    "white": "FFFFFF",
    "yellow": "FFFF00",
}

Rgba = tuple[int, int, int, int]


class ColorError(ValueError):
    """
    Raised when a color string cannot be resolved to RGBA channels.
    """


def parse_color(value: str, *, default_alpha: int = 0xFF) -> Rgba:
    """
    Resolve "red", "red@40", "#FF0000" or "#FF000055" to (r, g, b, a).

    An explicit alpha always wins. The "@<percent>" suffix is easier to reason
    about than a hex byte when picking a translucent overlay.

    Channels are returned rather than a "#RRGGBBAA" string so that busylib
    normalizes them. Passing hex strings would route through
    `pydantic_extra_types.color.Color.as_hex()`, whose short form collapses
    values such as "#FF000055" to "#f005" and loses the alpha.
    """
    spec = value.strip()
    alpha: int | None = None

    if "@" in spec:
        spec, _, percent = spec.partition("@")
        try:
            percent_value = float(percent)
        except ValueError:
            raise ColorError(
                f"invalid alpha percentage {percent!r} in {value!r}"
            ) from None
        if not 0.0 <= percent_value <= 100.0:
            raise ColorError(f"alpha percentage out of range 0-100 in {value!r}")
        alpha = round(percent_value * 255 / 100)

    spec = spec.strip()
    key = spec.lower()
    if key in NAMED_COLORS:
        digits = NAMED_COLORS[key]
    else:
        digits = spec.removeprefix("#").upper()
        if len(digits) == 8 and _is_hex(digits):
            if alpha is None:
                alpha = int(digits[6:], 16)
            digits = digits[:6]
        elif not (len(digits) == 6 and _is_hex(digits)):
            names = ", ".join(sorted(NAMED_COLORS))
            raise ColorError(
                f"unrecognised color {value!r}; use a name ({names}), "
                "#RRGGBB, or #RRGGBBAA, optionally with '@<percent>'"
            )

    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
        default_alpha if alpha is None else alpha,
    )


def _is_hex(value: str) -> bool:
    """
    Report whether every character is a hexadecimal digit.
    """
    return all(char in "0123456789ABCDEF" for char in value)
