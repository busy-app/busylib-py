from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from busylib import types


class AssetsClient(Protocol):
    """
    Protocol describing the async client surface used by asset sync.
    """

    async def storage_list(self, path: str) -> types.StorageList:
        """
        Return a listing of files in the given storage path.
        """
        ...

    async def storage_write(self, path: str, data: bytes) -> types.SuccessResponse:
        """
        Upload a file to device storage.
        """
        ...


logger = logging.getLogger(__name__)


async def sync_app_assets(
    client: AssetsClient,
    application_name: str,
    assets_dir: str | Path,
) -> list[str]:
    """
    Sync local assets with device storage for the given application name.
    Uploads files that are missing or have different sizes.
    """
    assets_path = Path(assets_dir)
    if not assets_path.is_dir():
        return []

    remote_dir = f"/ext/assets/{application_name}"
    try:
        listing = await client.storage_list(remote_dir)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to list remote assets: %s", exc)
        listing = types.StorageList(list=[])

    remote_sizes = {
        entry.name: entry.size
        for entry in listing.list
        if isinstance(entry, types.StorageFileElement)
    }

    uploaded: list[str] = []
    for local_path in sorted(assets_path.iterdir()):
        if not local_path.is_file():
            continue
        local_size = local_path.stat().st_size
        if remote_sizes.get(local_path.name) == local_size:
            continue
        data = local_path.read_bytes()
        await client.storage_write(f"{remote_dir}/{local_path.name}", data)
        uploaded.append(local_path.name)

    return uploaded
