from __future__ import annotations

import inspect

from busylib import exceptions, types
from busylib.client import AsyncBusyBar, BusyBar


def _doc_is_multiline(obj: object) -> bool:
    """
    Check that a docstring exists and spans multiple lines.

    Uses inspect.getdoc to normalize indentation before checking.
    """
    doc = inspect.getdoc(obj)
    return doc is not None and "\n" in doc


def test_core_docstrings_are_multiline() -> None:
    """
    Ensure core helpers and exceptions use multiline docstrings.

    This keeps public API documentation consistent with project rules.
    """
    targets = [
        BusyBar.usb_reset,
        AsyncBusyBar.usb_reset,
        exceptions.BusyBarAPIError,
        exceptions.BusyBarRequestError,
        exceptions.BusyBarAPIVersionError,
        exceptions.BusyBarUsbError,
        types.StrEnum,
    ]
    assert all(_doc_is_multiline(target) for target in targets)
