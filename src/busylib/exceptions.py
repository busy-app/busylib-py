from __future__ import annotations


class BusyBarAPIError(Exception):
    """Raised when the Busy Bar API returns an error response."""

    def __init__(self, error: str, code: int | None = None) -> None:
        self.error = error
        self.code = code
        message = error if code is None else f"{error} (code: {code})"
        super().__init__(message)


class BusyBarRequestError(Exception):
    """Raised when a request cannot be sent (network/timeout)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BusyBarAPIVersionError(Exception):
    """Raised when Busy Lib and device API versions are incompatible."""

    def __init__(self, *, library_version: str, device_version: str, message: str) -> None:
        self.library_version = library_version
        self.device_version = device_version
        super().__init__(message)
