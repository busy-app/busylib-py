from __future__ import annotations

from collections.abc import AsyncIterable, Iterable

import pytest

from busylib import types
from busylib.client.base import JsonType
from busylib.client.storage import AsyncStorageMixin, StorageMixin


class _DummyStorage(StorageMixin):
    """
    Minimal sync storage client that records request arguments.
    """

    def __init__(self) -> None:
        """
        Initialize a sync dummy client with a call log.
        """
        self.calls: list[dict[str, object]] = []

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_payload: JsonType | None = None,
        data: bytes | Iterable[bytes] | None = None,
        expect_bytes: bool = False,
        timeout: float | None = None,
    ) -> JsonType | bytes | str:
        """
        Record request arguments and return a success payload.
        """
        payload = data
        if data is not None and not isinstance(data, (bytes, bytearray)):
            payload = b"".join(data)
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "headers": headers,
                "json_payload": json_payload,
                "data": payload,
                "expect_bytes": expect_bytes,
                "timeout": timeout,
            }
        )
        if expect_bytes:
            return b"content"
        if path.endswith("/api/storage/list"):
            return {"list": []}
        return {"result": "ok"}


class _DummyAsyncStorage(AsyncStorageMixin):
    """
    Minimal async storage client that records request arguments.
    """

    def __init__(self) -> None:
        """
        Initialize an async dummy client with a call log.
        """
        self.calls: list[dict[str, object]] = []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_payload: JsonType | None = None,
        data: bytes | AsyncIterable[bytes] | None = None,
        expect_bytes: bool = False,
        timeout: float | None = None,
    ) -> JsonType | bytes | str:
        """
        Record async request arguments and return a success payload.
        """
        payload = data
        if data is not None and not isinstance(data, (bytes, bytearray)):
            chunks: list[bytes] = []
            async for chunk in data:
                chunks.append(chunk)
            payload = b"".join(chunks)
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "headers": headers,
                "json_payload": json_payload,
                "data": payload,
                "expect_bytes": expect_bytes,
                "timeout": timeout,
            }
        )
        if expect_bytes:
            return b"content"
        if path.endswith("/api/storage/list"):
            return {"list": []}
        return {"result": "ok"}


def test_write_storage_file_sync_progress(monkeypatch) -> None:
    """
    Verify sync write uses converted path and reports progress.
    """
    progress: list[tuple[int, int]] = []

    def _fake_convert(path: str, data: bytes) -> tuple[str, bytes]:
        """
        Return a deterministic converted path and payload.
        """
        return f"{path}.bin", data + b"!"

    def _on_progress(sent: int, total: int) -> None:
        """
        Capture progress reports to validate totals.
        """
        progress.append((sent, total))

    monkeypatch.setattr("busylib.client.storage.convert_for_storage", _fake_convert)
    client = _DummyStorage()

    resp = client.write_storage_file(
        "/ext/test.txt",
        b"abc",
        progress_callback=_on_progress,
        chunk_size=2,
    )

    call = client.calls[-1]
    assert call["method"] == "POST"
    assert call["path"] == "/api/storage/write"
    assert call["params"] == {"path": "/ext/test.txt.bin"}
    assert call["headers"] == {"Content-Length": "4"}
    assert call["data"] == b"abc!"
    assert isinstance(resp, types.SuccessResponse)
    assert progress[-1] == (4, 4)


@pytest.mark.asyncio
async def test_write_storage_file_async_progress(monkeypatch) -> None:
    """
    Verify async write uses converted path and reports progress.
    """
    progress: list[tuple[int, int]] = []

    def _fake_convert(path: str, data: bytes) -> tuple[str, bytes]:
        """
        Return a deterministic converted path and payload.
        """
        return f"{path}.bin", data + b"!"

    def _on_progress(sent: int, total: int) -> None:
        """
        Capture progress reports to validate totals.
        """
        progress.append((sent, total))

    monkeypatch.setattr("busylib.client.storage.convert_for_storage", _fake_convert)
    client = _DummyAsyncStorage()

    resp = await client.write_storage_file(
        "/ext/test.txt",
        b"abc",
        progress_callback=_on_progress,
        chunk_size=2,
    )

    call = client.calls[-1]
    assert call["method"] == "POST"
    assert call["path"] == "/api/storage/write"
    assert call["params"] == {"path": "/ext/test.txt.bin"}
    assert call["headers"] == {"Content-Length": "4"}
    assert call["data"] == b"abc!"
    assert isinstance(resp, types.SuccessResponse)
    assert progress[-1] == (4, 4)


def test_read_list_remove_sync() -> None:
    """
    Ensure sync storage read/list/remove wire the right requests.
    """
    client = _DummyStorage()
    client.read_storage_file("/ext/a.txt")
    client.list_storage_files("/ext")
    client.remove_storage_file("/ext/a.txt")

    assert client.calls[0]["path"] == "/api/storage/read"
    assert client.calls[0]["params"] == {"path": "/ext/a.txt"}
    assert client.calls[0]["expect_bytes"] is True
    assert client.calls[1]["path"] == "/api/storage/list"
    assert client.calls[1]["params"] == {"path": "/ext"}
    assert client.calls[2]["path"] == "/api/storage/remove"
    assert client.calls[2]["params"] == {"path": "/ext/a.txt"}


@pytest.mark.asyncio
async def test_read_list_remove_async() -> None:
    """
    Ensure async storage read/list/remove wire the right requests.
    """
    client = _DummyAsyncStorage()
    await client.read_storage_file("/ext/a.txt")
    await client.list_storage_files("/ext")
    await client.remove_storage_file("/ext/a.txt")

    assert client.calls[0]["path"] == "/api/storage/read"
    assert client.calls[0]["params"] == {"path": "/ext/a.txt"}
    assert client.calls[0]["expect_bytes"] is True
    assert client.calls[1]["path"] == "/api/storage/list"
    assert client.calls[1]["params"] == {"path": "/ext"}
    assert client.calls[2]["path"] == "/api/storage/remove"
    assert client.calls[2]["params"] == {"path": "/ext/a.txt"}
