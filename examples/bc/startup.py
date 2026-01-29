from __future__ import annotations

from busylib.exceptions import BusyBarAPIError

from .app_paths import app_assets_dir
from .runner import AsyncRunner


def ensure_app_directory(runner: AsyncRunner, app: str) -> str:
    """
    Ensure the app assets directory exists on the device.

    Returns the full assets path to use for uploads and navigation.
    """
    assets_path = app_assets_dir(app)
    client = runner.require_client()
    try:
        runner.run(client.list_storage_files(assets_path))
    except BusyBarAPIError as exc:
        if exc.code in {400, 404}:
            runner.run(client.create_storage_directory(assets_path))
        else:
            raise
    return assets_path
