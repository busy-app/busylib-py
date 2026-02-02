from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from busylib import types
from busylib.features import sync_app_assets


class _DummyAsyncClient:
    """
    Minimal async client stub for asset sync tests.
    """

    def __init__(self, listing: types.StorageList) -> None:
        """
        Store remote listing and captured writes.
        """
        self._listing = listing
        self.writes: list[tuple[str, bytes]] = []

    async def list_storage_files(self, path: str) -> types.StorageList:
        """
        Return a preconfigured storage listing.
        """
        await asyncio.sleep(0)
        return self._listing

    async def write_storage_file(self, path: str, data: bytes) -> types.SuccessResponse:
        """
        Record uploads and return a success response.
        """
        self.writes.append((path, data))
        return types.SuccessResponse(result="ok")


@pytest.mark.asyncio
async def test_sync_app_assets_uploads_missing(tmp_path: Path) -> None:
    """
    Upload local assets that are missing on the device.
    """
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "a.txt").write_text("hello", encoding="utf-8")
    listing = types.StorageList(list=[])
    client = _DummyAsyncClient(listing)

    uploaded = await sync_app_assets(client, "app", assets_dir)

    assert uploaded == ["a.txt"]
    assert client.writes[0][0] == "/ext/assets/app/a.txt"


@pytest.mark.asyncio
async def test_sync_app_assets_skips_same_size(tmp_path: Path) -> None:
    """
    Skip uploads when remote file size matches local.
    """
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "a.txt").write_text("hello", encoding="utf-8")
    listing = types.StorageList(list=[types.StorageFileElement(name="a.txt", size=5)])
    client = _DummyAsyncClient(listing)

    uploaded = await sync_app_assets(client, "app", assets_dir)

    assert uploaded == []
    assert client.writes == []
