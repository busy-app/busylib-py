from __future__ import annotations

import asyncio
import logging

from .base import AsyncClientBase, SyncClientBase
from ..converter import convert_for_storage
from .. import types

logger = logging.getLogger(__name__)


class StorageMixin(SyncClientBase):
    """
    File storage helpers for reading, writing, listing, and removing.
    """

    def write_storage_file(self, path: str, data: bytes) -> types.SuccessResponse:
        new_path, payload = convert_for_storage(path, data)
        logger.info("write_storage_file path=%s size=%s", new_path, len(payload))
        payload = self._request(
            "POST",
            "/api/storage/write",
            params={"path": new_path},
            data=payload,
        )
        return types.SuccessResponse.model_validate(payload)

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


class AsyncStorageMixin(AsyncClientBase):
    """
    Async file storage helpers for reading, writing, listing, and removing.
    """

    async def write_storage_file(self, path: str, data: bytes) -> types.SuccessResponse:
        new_path, payload = await asyncio.to_thread(convert_for_storage, path, data)
        logger.info("async write_storage_file path=%s size=%s", new_path, len(payload))
        payload = await self._request(
            "POST",
            "/api/storage/write",
            params={"path": new_path},
            data=payload,
        )
        return types.SuccessResponse.model_validate(payload)

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
