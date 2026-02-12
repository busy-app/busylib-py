from __future__ import annotations

from typing import Any


class BusyBarError(Exception):
    """
    Base class for all Busy Bar library exceptions.

    Allows callers to handle library failures via a single except clause.
    """


class BusyBarAPIError(BusyBarError):
    """
    Raised when the Busy Bar API returns an error response.

    Provides access to the response payload for diagnostics.
    """

    def __init__(
        self,
        error: str,
        code: int | None = None,
        *,
        status_code: int | None = None,
        method: str | None = None,
        path: str | None = None,
        payload: Any | None = None,
        request_id: str | None = None,
        response_excerpt: str | None = None,
    ) -> None:
        self.error = error
        self.code = code
        self.status_code = status_code
        self.method = method
        self.path = path
        self.payload = payload
        self.request_id = request_id
        self.response_excerpt = response_excerpt
        details = [error]
        if code is not None:
            details.append(f"code={code}")
        if status_code is not None:
            details.append(f"http={status_code}")
        if method and path:
            details.append(f"{method} {path}")
        if request_id:
            details.append(f"request_id={request_id}")
        message = " | ".join(details)
        super().__init__(message)


class BusyBarRequestError(BusyBarError):
    """
    Raised when a request cannot be sent (network/timeout).

    Used for transport-level failures before a response is received.
    """

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        path: str | None = None,
        attempts: int | None = None,
        original: Exception | None = None,
    ) -> None:
        self.method = method
        self.path = path
        self.attempts = attempts
        self.original = original
        super().__init__(message)


class BusyBarAPIVersionError(BusyBarError):
    """
    Raised when Busy Lib and device API versions are incompatible.

    Indicates that either firmware or library must be updated.
    """

    def __init__(
        self, *, library_version: str, device_version: str, message: str
    ) -> None:
        self.library_version = library_version
        self.device_version = device_version
        super().__init__(message)


class BusyBarUsbError(BusyBarError):
    """
    Raised when USB device is not connected or USB operation fails.

    Covers discovery, connection, and command execution issues.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BusyBarProtocolError(BusyBarError):
    """
    Raised when a successful HTTP response has an unexpected payload format.

    Used for 2xx responses that cannot be interpreted as required by endpoint.
    """

    def __init__(
        self,
        message: str,
        *,
        method: str,
        path: str,
        request_id: str | None = None,
        response_excerpt: str | None = None,
    ) -> None:
        self.method = method
        self.path = path
        self.request_id = request_id
        self.response_excerpt = response_excerpt
        details = [message, f"{method} {path}"]
        if request_id:
            details.append(f"request_id={request_id}")
        super().__init__(" | ".join(details))


class BusyBarResponseValidationError(BusyBarError):
    """
    Raised when a successful API response does not match expected schema.

    Wraps pydantic validation errors to keep a stable domain error contract.
    """

    def __init__(
        self,
        *,
        model: str,
        details: str,
        original: Exception | None = None,
    ) -> None:
        self.model = model
        self.details = details
        self.original = original
        super().__init__(f"Response validation failed for {model}: {details}")


class BusyBarWebSocketError(BusyBarError):
    """
    Raised when WebSocket connection or stream processing fails.

    Wraps low-level websocket library exceptions into a domain error type.
    """

    def __init__(
        self,
        message: str,
        *,
        path: str,
        original: Exception | None = None,
    ) -> None:
        self.path = path
        self.original = original
        super().__init__(f"{message} ({path})")
