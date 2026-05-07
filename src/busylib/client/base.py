from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterable, Iterable
from typing import Any, Literal, TypedDict

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .. import exceptions, versioning
from ..settings import settings

JsonType = dict[str, Any] | list[Any] | str | int | float | bool | None


class RequestKwargs(TypedDict, total=False):
    """
    Type low-level request context accepted by endpoint methods.

    Endpoint methods own their request body. For full body control use
    `api_request`, `prepare_request`, or `execute_prepared_request`.
    """

    params: dict[str, Any]
    headers: dict[str, str]
    session_id: str | None
    application_name: str | None
    timeout: float | httpx.Timeout | None


DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0, read=10.0, write=10.0, pool=5.0)
DEFAULT_BACKOFF = 0.25
LOCAL_CHECK_TIMEOUT = httpx.Timeout(1.5, connect=0.5, read=1.0, write=1.0, pool=0.5)
SESSION_HEADER = "x-session-id"
REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)
MAX_ERROR_EXCERPT = 256
MAX_LOG_BODY_EXCERPT = 512


class PreparedRequest(BaseModel):
    """
    Prepared low-level request ready for execution by HTTP clients.

    This object stores normalized request attributes after payload encoding.
    Callers can execute it with built-in client transport or pass fields to an
    external request executor. Serialization is not guaranteed because timeout
    and streaming content may contain runtime-only objects.

    Streaming content based on iterables/generators is single-use and should
    not be reused across multiple executions.
    """

    method: str
    path: str
    params: dict[str, Any] | None
    headers: dict[str, str] | None = Field(default=None, repr=False)
    content: bytes | Iterable[bytes] | AsyncIterable[bytes] | None = Field(
        default=None,
        repr=False,
    )
    expect_bytes: bool
    allow_text: bool
    timeout: httpx.Timeout
    request_id: str
    json_payload: JsonType | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _mask_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    """
    Return headers with sensitive auth values masked for safe logging.
    """
    if headers is None:
        return None
    hidden_keys = {"authorization", "x-api-token", "cookie", "set-cookie"}
    return {
        key: ("***" if key.lower() in hidden_keys else value)
        for key, value in headers.items()
    }


def _json_bytes(payload: Any) -> bytes:
    """
    Encode JSON payload as UTF-8 without ASCII escaping.
    """
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _data_length(data: Any) -> int | None:
    try:
        return len(data)  # type: ignore[arg-type]
    except Exception:
        return None


def _as_timeout(value: float | httpx.Timeout | None) -> httpx.Timeout:
    """
    Normalize timeout to an httpx.Timeout instance.
    """
    if value is None:
        return DEFAULT_TIMEOUT
    if isinstance(value, httpx.Timeout):
        return value
    return httpx.Timeout(value)


def _normalize_addr(addr: str) -> str:
    """
    Normalize an address to include a URL scheme.

    Falls back to http when the scheme is missing.
    """
    return addr if "://" in addr else f"http://{addr}"


def _truncate_text(value: str, limit: int = MAX_ERROR_EXCERPT) -> str:
    """
    Return a compact text excerpt suitable for exception diagnostics.
    """
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _get_header(headers: dict[str, str], name: str) -> str | None:
    """
    Return a header value using case-insensitive lookup.
    """
    name_lower = name.lower()
    return next(
        (value for key, value in headers.items() if key.lower() == name_lower),
        None,
    )


def _ensure_request_id(headers: dict[str, str]) -> str:
    """
    Return an existing request id or add a generated one to headers.
    """
    request_id = _get_header(headers, REQUEST_ID_HEADER)
    if request_id:
        return request_id
    request_id = uuid.uuid4().hex
    headers[REQUEST_ID_HEADER] = request_id
    return request_id


def _apply_application_name(
    method: str,
    application_name: str | None,
    params: dict[str, Any] | None,
    json_payload: JsonType | None,
) -> tuple[dict[str, Any] | None, JsonType | None]:
    """
    Attach application context to the request shape expected by the API.

    Mutating endpoints with object JSON carry the application context in the
    body. Read/delete and binary form endpoints keep it in query params.
    """
    if not application_name:
        return params, json_payload
    if method.upper() in {"POST", "PUT", "PATCH"} and isinstance(json_payload, dict):
        return params, {**json_payload, "application_name": application_name}
    params_local = dict(params or {})
    params_local["application_name"] = application_name
    return params_local, json_payload


def _prepare_request_payload(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None,
    headers: dict[str, str] | None,
    session_id: str | None,
    application_name: str | None,
    json_payload: JsonType | None,
    data: bytes | Iterable[bytes] | AsyncIterable[bytes] | None,
    expect_bytes: bool,
    allow_text: bool,
    timeout: float | httpx.Timeout | None,
    async_mode: bool,
) -> PreparedRequest:
    """
    Build a normalized PreparedRequest object from request parameters.

    The helper centralizes context headers, application placement, payload
    encoding, and safe request logging for sync and async clients.
    """
    headers_local: dict[str, str] = dict(headers or {})
    request_id = _ensure_request_id(headers_local)
    if session_id:
        headers_local[SESSION_HEADER] = session_id

    params_local, json_payload_local = _apply_application_name(
        method,
        application_name,
        params,
        json_payload,
    )
    content: bytes | Iterable[bytes] | AsyncIterable[bytes] | None = None
    serialized_json: bytes | None = None

    if json_payload_local is not None:
        serialized_json = _json_bytes(json_payload_local)
        content = serialized_json
        headers_local["Content-Type"] = "application/json; charset=utf-8"
    elif data is not None:
        content = data

    mode_label = "async " if async_mode else ""
    logger.debug(
        "Prepared %srequest %s %s request_id=%s params=%s headers=%s json_body=%s data_len=%s",
        mode_label,
        method,
        path,
        request_id,
        params_local,
        _mask_headers(headers_local or None),
        None
        if serialized_json is None
        else _truncate_text(serialized_json.decode("utf-8"), MAX_LOG_BODY_EXCERPT),
        None if data is None else _data_length(data),
    )

    return PreparedRequest(
        method=method,
        path=path,
        params=params_local,
        headers=headers_local or None,
        content=content,
        expect_bytes=expect_bytes,
        allow_text=allow_text,
        timeout=_as_timeout(timeout),
        request_id=request_id,
        json_payload=json_payload_local,
    )


def _response_request_id(response: httpx.Response, fallback: str) -> str:
    """
    Return response request id or the caller-generated fallback id.
    """
    return response.headers.get("X-Request-ID") or response.headers.get(
        "x-request-id", fallback
    )


def _raise_api_error_from_response(
    response: httpx.Response, *, prepared: PreparedRequest
) -> None:
    """
    Raise BusyBarAPIError built from an HTTP error response.

    The helper preserves the existing exception payload contract for both sync
    and async request execution paths.
    """
    payload = None
    request_id = _response_request_id(response, prepared.request_id)
    response_excerpt = _truncate_text(response.text)
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error") or payload.get("message")
            code = payload.get("code")
        else:
            error = None
            code = None
    except ValueError:
        error = f"HTTP {response.status_code}: {response_excerpt}"
        code = None

    if not error:
        error = response_excerpt or f"HTTP {response.status_code} error"

    logger.error(
        "API error %s request_id=%s: %s (body=%s)",
        code,
        request_id,
        error,
        response_excerpt,
    )
    raise exceptions.BusyBarAPIError(
        error=error,
        code=(code if isinstance(code, int) else response.status_code),
        status_code=response.status_code,
        method=prepared.method,
        path=prepared.path,
        payload=payload,
        request_id=request_id,
        response_excerpt=response_excerpt,
    )


def _decode_response_payload(
    response: httpx.Response, *, prepared: PreparedRequest
) -> JsonType | bytes | str:
    """
    Decode successful HTTP response according to PreparedRequest flags.

    Supports raw bytes mode and optional plain-text fallback when JSON is not
    available.
    """
    if prepared.expect_bytes:
        logger.debug(
            "Response %s %s status=%s bytes=%s",
            prepared.method,
            prepared.path,
            response.status_code,
            len(response.content),
        )
        return response.content

    try:
        logger.debug(
            "Response %s %s status=%s",
            prepared.method,
            prepared.path,
            response.status_code,
        )
        return response.json()
    except ValueError:
        if not prepared.allow_text:
            raise exceptions.BusyBarProtocolError(
                "Expected JSON response body",
                method=prepared.method,
                path=prepared.path,
                request_id=_response_request_id(response, prepared.request_id),
                response_excerpt=_truncate_text(response.text),
            )
        logger.debug(
            "Response %s %s status=%s (text fallback)",
            prepared.method,
            prepared.path,
            response.status_code,
        )
        return response.text


class SyncClientBase:
    """
    Sync foundation: connection setup, retries, and low-level HTTP requests.
    """

    connection_type: Literal["local", "cloud", "network"] = "network"

    def __init__(
        self,
        addr: str | None = None,
        *,
        token: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int = 2,
        backoff: float = DEFAULT_BACKOFF,
        transport: httpx.BaseTransport | None = None,
        api_version: str | None = None,
    ) -> None:
        if addr is None and token is None:
            self.base_url = settings.base_url
            self.connection_type = "local"
        elif addr is None:
            self.base_url = settings.cloud_base_url
            self.connection_type = "cloud"
        else:
            self.base_url = _normalize_addr(addr)
            self.connection_type = "network"

        self._token = token
        self.max_retries = max(0, int(max_retries))
        self.backoff = backoff
        self.api_version = api_version or versioning.API_VERSION
        self._device_api_version: str | None = None

        headers: dict[str, str] = {versioning.API_VERSION_HEADER: self.api_version}
        if token is None:
            pass
        elif self.is_cloud:
            headers["Authorization"] = f"Bearer {token}"
        else:
            headers["X-API-Token"] = token

        self.client = httpx.Client(
            base_url=self.base_url,
            headers=headers or None,
            timeout=_as_timeout(timeout),
            transport=transport,
        )

    @property
    def is_cloud(self) -> bool:
        """
        Check whether connection uses cloud mode.

        Returns True for cloud connection_type.
        """
        return self.connection_type == "cloud"

    @property
    def is_local(self) -> bool:
        """
        Check whether connection uses local mode.

        Returns True for local connection_type.
        """
        return self.connection_type == "local"

    def is_local_available(self) -> bool:
        """
        Check local API reachability on base_url.

        Returns True when /api/version responds without network errors.
        """
        base_url = _normalize_addr(settings.base_url).rstrip("/")
        url = f"{base_url}/api/version"
        headers = {versioning.API_VERSION_HEADER: self.api_version}
        if self._token:
            headers["X-API-Token"] = self._token
        try:
            response = self.client.get(
                url,
                headers=headers,
                timeout=LOCAL_CHECK_TIMEOUT,
            )
        except httpx.RequestError:
            return False
        return response.status_code < 400

    def __enter__(self) -> SyncClientBase:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def api_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        session_id: str | None = None,
        application_name: str | None = None,
        json_payload: JsonType | None = None,
        data: bytes | Iterable[bytes] | None = None,
        expect_bytes: bool = False,
        allow_text: bool = False,
        timeout: float | httpx.Timeout | None = None,
    ) -> JsonType | bytes | str:
        """
        Execute a raw API request through the current client session.

        Advanced callers can control path, params, headers, body, and request
        context without creating a separate HTTP client.
        """
        return self._request(
            method,
            path,
            params=params,
            headers=headers,
            session_id=session_id,
            application_name=application_name,
            json_payload=json_payload,
            data=data,
            expect_bytes=expect_bytes,
            allow_text=allow_text,
            timeout=timeout,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        session_id: str | None = None,
        application_name: str | None = None,
        json_payload: JsonType | None = None,
        data: bytes | Iterable[bytes] | None = None,
        expect_bytes: bool = False,
        allow_text: bool = False,
        timeout: float | httpx.Timeout | None = None,
    ) -> JsonType | bytes | str:
        """
        Prepare and execute one synchronous HTTP request.

        This convenience wrapper preserves existing behavior while delegating
        preparation and execution to dedicated methods.
        """
        prepared = self.prepare_request(
            method,
            path,
            params=params,
            headers=headers,
            session_id=session_id,
            application_name=application_name,
            json_payload=json_payload,
            data=data,
            expect_bytes=expect_bytes,
            allow_text=allow_text,
            timeout=timeout,
        )
        return self.execute_prepared_request(prepared)

    def prepare_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        session_id: str | None = None,
        application_name: str | None = None,
        json_payload: JsonType | None = None,
        data: bytes | Iterable[bytes] | None = None,
        expect_bytes: bool = False,
        allow_text: bool = False,
        timeout: float | httpx.Timeout | None = None,
    ) -> PreparedRequest:
        """
        Build a prepared request without executing network I/O.

        External integrations can inspect the prepared payload, route it to
        custom transports, or execute later via `execute_prepared_request`.
        """
        return _prepare_request_payload(
            method,
            path,
            params=params,
            headers=headers,
            session_id=session_id,
            application_name=application_name,
            json_payload=json_payload,
            data=data,
            expect_bytes=expect_bytes,
            allow_text=allow_text,
            timeout=timeout,
            async_mode=False,
        )

    def execute_prepared_request(
        self,
        prepared: PreparedRequest,
        *,
        client: httpx.Client | None = None,
    ) -> JsonType | bytes | str:
        """
        Execute a previously prepared request.

        By default the current `httpx.Client` is used. Callers may inject a
        custom client while preserving error mapping. Prepared streaming content
        is single-use and should be regenerated for repeated executions.
        """
        request_client = client or self.client
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = request_client.request(
                    prepared.method,
                    prepared.path,
                    params=prepared.params,
                    content=prepared.content,
                    headers=prepared.headers,
                    timeout=prepared.timeout,
                )
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise exceptions.BusyBarRequestError(
                        str(exc),
                        method=prepared.method,
                        path=prepared.path,
                        request_id=prepared.request_id,
                        attempts=attempt + 1,
                        original=exc,
                    ) from exc
                time.sleep(self.backoff * (attempt + 1))
                continue

            if response.status_code >= 400:
                _raise_api_error_from_response(response, prepared=prepared)
            return _decode_response_payload(response, prepared=prepared)

        if last_exc:
            raise exceptions.BusyBarRequestError(
                str(last_exc),
                method=prepared.method,
                path=prepared.path,
                request_id=prepared.request_id,
                attempts=self.max_retries + 1,
                original=last_exc,
            ) from last_exc
        raise exceptions.BusyBarRequestError(
            "Unknown request error",
            method=prepared.method,
            path=prepared.path,
            request_id=prepared.request_id,
            attempts=self.max_retries + 1,
        )


class AsyncClientBase:
    """
    Async foundation: connection setup, retries, and low-level HTTP requests.
    """

    connection_type: Literal["local", "cloud", "network"] = "network"

    def __init__(
        self,
        addr: str | None = None,
        *,
        token: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int = 2,
        backoff: float = DEFAULT_BACKOFF,
        transport: httpx.AsyncBaseTransport | None = None,
        api_version: str | None = None,
    ) -> None:
        if addr is None and token is None:
            self.base_url = settings.base_url
            self.connection_type = "local"
        elif addr is None:
            self.base_url = settings.cloud_base_url
            self.connection_type = "cloud"
        else:
            self.base_url = _normalize_addr(addr)
            self.connection_type = "network"

        self._token = token
        self.max_retries = max(0, int(max_retries))
        self.backoff = backoff
        self.api_version = api_version or versioning.API_VERSION
        self._device_api_version: str | None = None

        headers: dict[str, str] = {versioning.API_VERSION_HEADER: self.api_version}
        if token is None:
            pass
        elif self.is_cloud:
            headers["Authorization"] = f"Bearer {token}"
        else:
            headers["X-API-Token"] = token

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers or None,
            timeout=_as_timeout(timeout),
            transport=transport,
        )

    @property
    def is_cloud(self) -> bool:
        """
        Check whether connection uses cloud mode.

        Returns True for cloud connection_type.
        """
        return self.connection_type == "cloud"

    @property
    def is_local(self) -> bool:
        """
        Check whether connection uses local mode.

        Returns True for local connection_type.
        """
        return self.connection_type == "local"

    async def is_local_available(self) -> bool:
        """
        Check local API reachability on base_url.

        Returns True when /api/version responds without network errors.
        """
        base_url = _normalize_addr(settings.base_url).rstrip("/")
        url = f"{base_url}/api/version"
        headers = {versioning.API_VERSION_HEADER: self.api_version}
        if self._token:
            headers["X-API-Token"] = self._token
        try:
            response = await self.client.get(
                url,
                headers=headers,
                timeout=LOCAL_CHECK_TIMEOUT,
            )
        except httpx.RequestError:
            return False
        return response.status_code < 400

    async def __aenter__(self) -> AsyncClientBase:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.client.aclose()

    async def api_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        session_id: str | None = None,
        application_name: str | None = None,
        json_payload: JsonType | None = None,
        data: bytes | AsyncIterable[bytes] | None = None,
        expect_bytes: bool = False,
        allow_text: bool = False,
        timeout: float | httpx.Timeout | None = None,
    ) -> JsonType | bytes | str:
        """
        Execute a raw async API request through the current client session.

        Advanced callers can control path, params, headers, body, and request
        context without creating a separate HTTP client.
        """
        return await self._request(
            method,
            path,
            params=params,
            headers=headers,
            session_id=session_id,
            application_name=application_name,
            json_payload=json_payload,
            data=data,
            expect_bytes=expect_bytes,
            allow_text=allow_text,
            timeout=timeout,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        session_id: str | None = None,
        application_name: str | None = None,
        json_payload: JsonType | None = None,
        data: bytes | AsyncIterable[bytes] | None = None,
        expect_bytes: bool = False,
        allow_text: bool = False,
        timeout: float | httpx.Timeout | None = None,
    ) -> JsonType | bytes | str:
        """
        Prepare and execute one asynchronous HTTP request.

        This convenience wrapper preserves existing behavior while delegating
        preparation and execution to dedicated methods.
        """
        prepared = self.prepare_request(
            method,
            path,
            params=params,
            headers=headers,
            session_id=session_id,
            application_name=application_name,
            json_payload=json_payload,
            data=data,
            expect_bytes=expect_bytes,
            allow_text=allow_text,
            timeout=timeout,
        )
        return await self.execute_prepared_request(prepared)

    def prepare_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        session_id: str | None = None,
        application_name: str | None = None,
        json_payload: JsonType | None = None,
        data: bytes | AsyncIterable[bytes] | None = None,
        expect_bytes: bool = False,
        allow_text: bool = False,
        timeout: float | httpx.Timeout | None = None,
    ) -> PreparedRequest:
        """
        Build a prepared async request without executing network I/O.

        External integrations can inspect the prepared payload, route it to
        custom transports, or execute later via `execute_prepared_request`.
        Prepared request should be executed with an async executor.
        """
        return _prepare_request_payload(
            method,
            path,
            params=params,
            headers=headers,
            session_id=session_id,
            application_name=application_name,
            json_payload=json_payload,
            data=data,
            expect_bytes=expect_bytes,
            allow_text=allow_text,
            timeout=timeout,
            async_mode=True,
        )

    async def execute_prepared_request(
        self,
        prepared: PreparedRequest,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> JsonType | bytes | str:
        """
        Execute a previously prepared async request.

        By default the current `httpx.AsyncClient` is used. Callers may inject
        a custom client while preserving error mapping. Prepared streaming
        content is single-use and should be regenerated for repeated executions.
        """
        request_client = client or self.client
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await request_client.request(
                    prepared.method,
                    prepared.path,
                    params=prepared.params,
                    content=prepared.content,
                    headers=prepared.headers,
                    timeout=prepared.timeout,
                )
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise exceptions.BusyBarRequestError(
                        str(exc),
                        method=prepared.method,
                        path=prepared.path,
                        request_id=prepared.request_id,
                        attempts=attempt + 1,
                        original=exc,
                    ) from exc
                await asyncio.sleep(self.backoff * (attempt + 1))
                continue

            if response.status_code >= 400:
                _raise_api_error_from_response(response, prepared=prepared)
            return _decode_response_payload(response, prepared=prepared)

        if last_exc:
            raise exceptions.BusyBarRequestError(
                str(last_exc),
                method=prepared.method,
                path=prepared.path,
                request_id=prepared.request_id,
                attempts=self.max_retries + 1,
                original=last_exc,
            ) from last_exc
        raise exceptions.BusyBarRequestError(
            "Unknown request error",
            method=prepared.method,
            path=prepared.path,
            request_id=prepared.request_id,
            attempts=self.max_retries + 1,
        )
