from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterator

from .. import types
from ..converter import convert_for_storage
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)


class StorageMixin(SyncClientBase):
    """
    File storage helpers for reading, writing, listing, and removing.
    """

    def write_storage_file(
        self,
        path: str,
        data: bytes,
        *,
        timeout: float | None = 60.0,
        progress_callback: Callable[[int, int], None] | None = None,
        chunk_size: int = 64 * 1024,
    ) -> types.SuccessResponse:
        new_path, payload = convert_for_storage(path, data)
        total = len(payload)
        logger.info("write_storage_file path=%s size=%s", new_path, total)

        def _iter_payload() -> Iterator[bytes]:
            sent = 0
            for i in range(0, total, chunk_size):
                chunk = payload[i : i + chunk_size]
                sent += len(chunk)
                if progress_callback:
                    progress_callback(sent, total)
                yield chunk

        response = self._request(
            "POST",
            "/api/storage/write",
            params={"path": new_path},
            headers={"Content-Length": str(total)} if progress_callback else None,
            data=_iter_payload() if progress_callback else payload,
            timeout=timeout,
        )
        return types.SuccessResponse.model_validate(response)

    def read_storage_file(self, path: str) -> bytes:
        logger.info("read_storage_file path=%s", path)
        return self._request(
            "GET",
            "/api/storage/read",
            params={"path": path},
            expect_bytes=True,
        )  # type: ignore[return-value]

    def list_storage_files(self, path: str) -> types.StorageList:
        logger.info("list_storage_files path=%s", path)
        data = self._request(
            "GET",
            "/api/storage/list",
            params={"path": path},
        )
        return types.StorageList.model_validate(data)

    def remove_storage_file(self, path: str) -> types.SuccessResponse:
        logger.info("remove_storage_file path=%s", path)
        data = self._request(
            "DELETE",
            "/api/storage/remove",
            params={"path": path},
        )
        return types.SuccessResponse.model_validate(data)

    def create_storage_directory(self, path: str) -> types.SuccessResponse:
        logger.info("create_storage_directory path=%s", path)
        data = self._request(
            "POST",
            "/api/storage/mkdir",
            params={"path": path},
        )
        return types.SuccessResponse.model_validate(data)

    def get_storage_status(self) -> types.StorageStatus:
        logger.info("get_storage_status")
        data = self._request(
            "GET",
            "/api/storage/status",
        )
        return types.StorageStatus.model_validate(data)


class AsyncStorageMixin(AsyncClientBase):
    """
    Async file storage helpers for reading, writing, listing, and removing.
    """

    async def write_storage_file(
        self,
        path: str,
        data: bytes,
        *,
        timeout: float | None = 60.0,
        progress_callback: Callable[[int, int], None] | None = None,
        chunk_size: int = 64 * 1024,
    ) -> types.SuccessResponse:
        new_path, payload = await asyncio.to_thread(convert_for_storage, path, data)
        total = len(payload)
        logger.info("async write_storage_file path=%s size=%s", new_path, total)

        async def _aiter_payload() -> AsyncIterator[bytes]:
            sent = 0
            for i in range(0, total, chunk_size):
                chunk = payload[i : i + chunk_size]
                sent += len(chunk)
                if progress_callback:
                    progress_callback(sent, total)
                yield chunk

        response = await self._request(
            "POST",
            "/api/storage/write",
            params={"path": new_path},
            headers={"Content-Length": str(total)} if progress_callback else None,
            data=_aiter_payload() if progress_callback else payload,
            timeout=timeout,
        )
        return types.SuccessResponse.model_validate(response)

    async def read_storage_file(self, path: str) -> bytes:
        logger.info("async read_storage_file path=%s", path)
        return await self._request(
            "GET",
            "/api/storage/read",
            params={"path": path},
            expect_bytes=True,
        )  # type: ignore[return-value]

    async def list_storage_files(self, path: str) -> types.StorageList:
        logger.info("async list_storage_files path=%s", path)
        data = await self._request(
            "GET",
            "/api/storage/list",
            params={"path": path},
        )
        return types.StorageList.model_validate(data)

    async def remove_storage_file(self, path: str) -> types.SuccessResponse:
        logger.info("async remove_storage_file path=%s", path)
        data = await self._request(
            "DELETE",
            "/api/storage/remove",
            params={"path": path},
        )
        return types.SuccessResponse.model_validate(data)

    async def create_storage_directory(self, path: str) -> types.SuccessResponse:
        logger.info("async create_storage_directory path=%s", path)
        data = await self._request(
            "POST",
            "/api/storage/mkdir",
            params={"path": path},
        )
        return types.SuccessResponse.model_validate(data)

    async def get_storage_status(self) -> types.StorageStatus:
        logger.info("async get_storage_status")
        data = await self._request(
            "GET",
            "/api/storage/status",
        )
        return types.StorageStatus.model_validate(data)
