from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterable, Iterable
from typing import Any, Literal

import httpx

from .. import exceptions, versioning
from ..settings import settings

JsonType = dict[str, Any] | list[Any] | str | int | float | bool | None


DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0, read=10.0, write=10.0, pool=5.0)
DEFAULT_BACKOFF = 0.25
LOCAL_CHECK_TIMEOUT = httpx.Timeout(1.5, connect=0.5, read=1.0, write=1.0, pool=0.5)

logger = logging.getLogger(__name__)


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
        Проверить, что соединение идёт через облако.

        Возвращает True для cloud connection_type.
        """
        return self.connection_type == "cloud"

    @property
    def is_local(self) -> bool:
        """
        Проверить, что соединение идёт через локальный адрес.

        Возвращает True для local connection_type.
        """
        return self.connection_type == "local"

    def is_local_available(self) -> bool:
        """
        Проверить доступность локального API на base_url.

        Возвращает True, если /api/version отвечает без ошибок сети.
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

    def __enter__(self) -> "SyncClientBase":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_payload: JsonType | None = None,
        data: bytes | Iterable[bytes] | None = None,
        expect_bytes: bool = False,
        timeout: float | httpx.Timeout | None = None,
    ) -> JsonType | bytes | str:
        headers_local: dict[str, str] = dict(headers or {})
        content: bytes | Iterable[bytes] | None = None
        serialized_json = None

        if json_payload is not None:
            serialized_json = _json_bytes(json_payload)
            content = serialized_json
            headers_local["Content-Type"] = "application/json; charset=utf-8"
        elif data is not None:
            content = data

        logger.debug(
            "Sending request %s %s params=%s headers=%s json_body=%s data_len=%s",
            method,
            path,
            params,
            headers_local or None,
            None if serialized_json is None else serialized_json.decode("utf-8"),
            None if data is None else _data_length(data),
        )

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.request(
                    method,
                    path,
                    params=params,
                    content=content,
                    headers=headers_local or None,
                    timeout=_as_timeout(timeout),
                )
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise exceptions.BusyBarRequestError(str(exc)) from exc
                time.sleep(self.backoff * (attempt + 1))
                continue

            if response.status_code >= 400:
                try:
                    payload = response.json()
                    error = (
                        payload.get("error") or payload.get("message") or response.text
                    )
                    code = payload.get("code", response.status_code)
                except json.JSONDecodeError:
                    error = f"HTTP {response.status_code}: {response.text}"
                    code = response.status_code
                logger.error("API error %s: %s (body=%s)", code, error, response.text)
                raise exceptions.BusyBarAPIError(error=error, code=code)

            if expect_bytes:
                logger.debug(
                    "Response %s %s status=%s bytes=%s",
                    method,
                    path,
                    response.status_code,
                    len(response.content),
                )
                return response.content

            try:
                logger.debug(
                    "Response %s %s status=%s", method, path, response.status_code
                )
                return response.json()
            except json.JSONDecodeError:
                logger.debug(
                    "Response %s %s status=%s (text fallback)",
                    method,
                    path,
                    response.status_code,
                )
                return response.text

        if last_exc:
            raise last_exc
        raise exceptions.BusyBarRequestError("Unknown request error")


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
        Проверить, что соединение идёт через облако.

        Возвращает True для cloud connection_type.
        """
        return self.connection_type == "cloud"

    @property
    def is_local(self) -> bool:
        """
        Проверить, что соединение идёт через локальный адрес.

        Возвращает True для local connection_type.
        """
        return self.connection_type == "local"

    async def is_local_available(self) -> bool:
        """
        Проверить доступность локального API на base_url.

        Возвращает True, если /api/version отвечает без ошибок сети.
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

    async def __aenter__(self) -> "AsyncClientBase":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_payload: JsonType | None = None,
        data: bytes | AsyncIterable[bytes] | None = None,
        expect_bytes: bool = False,
        timeout: float | httpx.Timeout | None = None,
    ) -> JsonType | bytes | str:
        headers_local: dict[str, str] = dict(headers or {})
        content: bytes | AsyncIterable[bytes] | None = None
        serialized_json = None

        if json_payload is not None:
            serialized_json = _json_bytes(json_payload)
            content = serialized_json
            headers_local["Content-Type"] = "application/json; charset=utf-8"
        elif data is not None:
            content = data

        logger.debug(
            "Sending async request %s %s params=%s headers=%s json_body=%s data_len=%s",
            method,
            path,
            params,
            headers_local or None,
            None if serialized_json is None else serialized_json.decode("utf-8"),
            None if data is None else _data_length(data),
        )

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.request(
                    method,
                    path,
                    params=params,
                    content=content,
                    headers=headers_local or None,
                    timeout=_as_timeout(timeout),
                )
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise exceptions.BusyBarRequestError(str(exc)) from exc
                await asyncio.sleep(self.backoff * (attempt + 1))
                continue

            if response.status_code >= 400:
                try:
                    payload = response.json()
                    error = (
                        payload.get("error") or payload.get("message") or response.text
                    )
                    code = payload.get("code", response.status_code)
                except json.JSONDecodeError:
                    error = f"HTTP {response.status_code}: {response.text}"
                    code = response.status_code
                raise exceptions.BusyBarAPIError(error=error, code=code)

            if expect_bytes:
                logger.debug(
                    "Response %s %s status=%s bytes=%s",
                    method,
                    path,
                    response.status_code,
                    len(response.content),
                )
                return response.content

            try:
                logger.debug(
                    "Response %s %s status=%s", method, path, response.status_code
                )
                return response.json()
            except json.JSONDecodeError:
                logger.debug(
                    "Response %s %s status=%s (text fallback)",
                    method,
                    path,
                    response.status_code,
                )
                return response.text

        if last_exc:
            raise last_exc
        raise exceptions.BusyBarRequestError("Unknown request error")
