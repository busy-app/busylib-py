"""
Helpers shared between the bundled examples.

These mirror device-side rules (name validation) or resolve user input the
way the device expects it (timezones), so they belong next to both the
`remote` and `setup` examples rather than inside either one.
"""

from examples.shared.discovery import resolve_connection
from examples.shared.device_name import (
    ALLOWED_SPECIAL_CHARS,
    MAX_NAME_LENGTH,
    validate_device_name,
)
from examples.shared.timezones import resolve_timezone

__all__ = [
    "ALLOWED_SPECIAL_CHARS",
    "resolve_connection",
    "MAX_NAME_LENGTH",
    "resolve_timezone",
    "validate_device_name",
]
