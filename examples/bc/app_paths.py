from __future__ import annotations


def app_assets_dir(app: str) -> str:
    """
    Build the storage path for an app assets directory.

    Keeps assets under /ext/assets/<app> for BusyBar storage.
    """
    return f"/ext/assets/{app}"
