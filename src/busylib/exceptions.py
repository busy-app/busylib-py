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
        request_id: str | None = None,
        attempts: int | None = None,
        original: Exception | None = None,
    ) -> None:
        self.message = message
        self.method = method
        self.path = path
        self.request_id = request_id
        self.attempts = attempts
        self.original = original
        details = [message]
        if method and path:
            details.append(f"{method} {path}")
        if request_id:
            details.append(f"request_id={request_id}")
        if attempts is not None:
            details.append(f"attempts={attempts}")
        super().__init__(" | ".join(details))


def is_retryable_delivery_error(error: BusyBarError) -> bool:
    """
    Classify Busy Bar delivery failures for caller retry decisions.

    Treats request/transport failures and explicitly transient HTTP statuses
    as retryable. Other 4xx responses are caller or authorization problems and
    should not be retried as-is.
    """

    if isinstance(error, BusyBarAPIError):
        return error.status_code in {408, 429, 500, 502, 503, 504}
    return isinstance(error, BusyBarRequestError)


def format_delivery_error(error: BusyBarError) -> str:
    """
    Format Busy Bar delivery failure into a compact diagnostic string.

    Keeps enough HTTP context and response body excerpt for service logs without
    duplicating full response-formatting logic in each integration.
    """

    if isinstance(error, BusyBarAPIError):
        details = [
            f"HTTP {error.status_code}" if error.status_code else "API error",
            f"{error.method} {error.path}" if error.method and error.path else "",
            error.error,
        ]
        if error.request_id:
            details.append(f"request_id={error.request_id}")
        if error.response_excerpt:
            details.append(f"body={error.response_excerpt}")
        return " | ".join(detail for detail in details if detail)

    if isinstance(error, BusyBarRequestError):
        details = [
            "request error",
            f"{error.method} {error.path}" if error.method and error.path else "",
            f"request_id={error.request_id}" if error.request_id else "",
            f"attempts={error.attempts}" if error.attempts else "",
            error.message,
        ]
        return " | ".join(detail for detail in details if detail)

    return str(error)


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


class BusyBarConversionError(BusyBarError):
    """
    Raised when local file conversion fails before upload to the device.

    Used by storage upload flows to report unsupported formats and failed
    conversion pipelines with a stable domain exception type.
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
        detail = f": {original}" if original is not None else ""
        super().__init__(f"{message} ({path}){detail}")
