from __future__ import annotations

# Mirrors the firmware's own rules in
# `applications/services/device_name/device_name.c` so invalid names are
# rejected locally with a clear reason instead of an opaque API error.
MAX_NAME_LENGTH = 20
ALLOWED_SPECIAL_CHARS = " !()-_=+;:,.?'|@#$%^&*[]{}/\\\"<>"


def _is_valid_char(char: str) -> bool:
    """
    Check one character against the firmware's allowed set.

    The firmware accepts ASCII alphanumerics plus a fixed punctuation set,
    and rejects anything non-ASCII, so `isascii()` must be checked before
    `isalnum()` (which is true for non-ASCII letters in Python).
    """
    return char.isascii() and (char.isalnum() or char in ALLOWED_SPECIAL_CHARS)


def validate_device_name(name: str) -> str | None:
    """
    Validate a device name, returning an error message or None if valid.

    Checks run in the same order as the firmware's `device_name_validate()`
    so the reported reason matches what the device itself would report. The
    full rule set is kept even where a caller pre-empts one - `name_set`
    strips first, but the remote wizard's prompt does not, so a spaces-only
    name can still reach the "only spaces" branch.
    """
    if not name:
        return "name is empty"

    for char in name:
        if not _is_valid_char(char):
            return f"illegal character {char!r}"

    if all(char == " " for char in name):
        return "name consists only of spaces"

    if len(name) > MAX_NAME_LENGTH:
        return f"name is longer than {MAX_NAME_LENGTH} characters"

    return None
