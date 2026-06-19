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

    def storage_write(
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
        logger.info("storage_write path=%s size=%s", new_path, total)

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

    def storage_read(self, path: str) -> bytes:
        logger.info("storage_read path=%s", path)
        return self._request(
            "GET",
            "/api/storage/read",
            params={"path": path},
            expect_bytes=True,
        )  # type: ignore[return-value]

    def storage_list(self, path: str) -> types.StorageList:
        logger.info("storage_list path=%s", path)
        data = self._request(
            "GET",
            "/api/storage/list",
            params={"path": path},
        )
        return types.StorageList.model_validate(data)

    def storage_remove(self, path: str) -> types.SuccessResponse:
        logger.info("storage_remove path=%s", path)
        data = self._request(
            "DELETE",
            "/api/storage/remove",
            params={"path": path},
        )
        return types.SuccessResponse.model_validate(data)

    def storage_mkdir(self, path: str) -> types.SuccessResponse:
        """
        Create a storage directory via POST /api/storage/mkdir.
        """
        logger.info("storage_mkdir path=%s", path)
        data = self._request(
            "POST",
            "/api/storage/mkdir",
            params={"path": path},
        )
        return types.SuccessResponse.model_validate(data)

    def storage_rename(self, old_path: str, new_path: str) -> types.SuccessResponse:
        """
        Rename a storage entry via POST /api/storage/rename.
        """
        logger.info("storage_rename old_path=%s new_path=%s", old_path, new_path)
        data = self._request(
            "POST",
            "/api/storage/rename",
            params={"old_path": old_path, "new_path": new_path},
        )
        return types.SuccessResponse.model_validate(data)

    def storage_status(self) -> types.StorageStatus:
        logger.info("storage_status")
        data = self._request(
            "GET",
            "/api/storage/status",
        )
        return types.StorageStatus.model_validate(data)


class AsyncStorageMixin(AsyncClientBase):
    """
    Async file storage helpers for reading, writing, listing, and removing.
    """

    async def storage_write(
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
        logger.info("async storage_write path=%s size=%s", new_path, total)

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

    async def storage_read(self, path: str) -> bytes:
        logger.info("async storage_read path=%s", path)
        return await self._request(
            "GET",
            "/api/storage/read",
            params={"path": path},
            expect_bytes=True,
        )  # type: ignore[return-value]

    async def storage_list(self, path: str) -> types.StorageList:
        logger.info("async storage_list path=%s", path)
        data = await self._request(
            "GET",
            "/api/storage/list",
            params={"path": path},
        )
        return types.StorageList.model_validate(data)

    async def storage_remove(self, path: str) -> types.SuccessResponse:
        logger.info("async storage_remove path=%s", path)
        data = await self._request(
            "DELETE",
            "/api/storage/remove",
            params={"path": path},
        )
        return types.SuccessResponse.model_validate(data)

    async def storage_mkdir(self, path: str) -> types.SuccessResponse:
        """
        Create a storage directory via POST /api/storage/mkdir.
        """
        logger.info("async storage_mkdir path=%s", path)
        data = await self._request(
            "POST",
            "/api/storage/mkdir",
            params={"path": path},
        )
        return types.SuccessResponse.model_validate(data)

    async def storage_rename(
        self, old_path: str, new_path: str
    ) -> types.SuccessResponse:
        """
        Rename a storage entry via POST /api/storage/rename.
        """
        logger.info("async storage_rename old_path=%s new_path=%s", old_path, new_path)
        data = await self._request(
            "POST",
            "/api/storage/rename",
            params={"old_path": old_path, "new_path": new_path},
        )
        return types.SuccessResponse.model_validate(data)

    async def storage_status(self) -> types.StorageStatus:
        logger.info("async storage_status")
        data = await self._request(
            "GET",
            "/api/storage/status",
        )
        return types.StorageStatus.model_validate(data)
