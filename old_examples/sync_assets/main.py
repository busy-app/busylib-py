"""
Sync local assets directory with device storage.

Defaults are controlled by env vars:
- BUSYBAR_ADDR (default: http://10.0.4.20)
- BUSY_LAN_TOKEN (optional LAN token, sent as x-api-token)
- BUSY_CLOUD_TOKEN (optional bearer for cloud)
- BUSYBAR_ASSETS_DIR (default: assets)
- BUSYBAR_APP_ID (default: busylib-demo)
"""

import argparse
from pathlib import Path

from busylib import BusyBar


def safe_call(label, func, *args, **kwargs):
    try:
        result = func(*args, **kwargs)
        print(f"{label}: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        print(f"{label} failed: {exc}")
        return None


def sync_assets(client: BusyBar, app_id: str, assets_dir: str) -> None:
    assets_path = Path(assets_dir)
    if not assets_path.is_dir():
        print(f"sync_assets skipped: assets dir not found ({assets_path})")
        return

    local_files = {path.name: path for path in assets_path.iterdir() if path.is_file()}
    remote_dir = f"/ext/assets/{app_id}"
    remote_list = safe_call("list_storage_files", client.list_storage_files, remote_dir)

    remote_files = set()
    remote_sizes = {}
    if remote_list:
        for item in remote_list.list:
            if getattr(item, "type", None) == "file":
                remote_files.add(item.name)
                remote_sizes[item.name] = item.size

    for filename, path in sorted(local_files.items()):
        local_size = path.stat().st_size
        remote_size = remote_sizes.get(filename)
        if remote_size == local_size:
            print(f"sync_assets skip (same size): {filename}")
            continue
        safe_call(
            f"upload_asset ({filename})",
            client.upload_asset,
            app_id,
            filename,
            path.read_bytes(),
        )

    for filename in sorted(remote_files - set(local_files.keys())):
        safe_call(
            f"remove_storage_file ({filename})",
            client.remove_storage_file,
            f"{remote_dir}/{filename}",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync local assets with BusyBar device storage.")
    parser.add_argument("--addr", default=None, help="Device address (defaults to BUSYBAR_ADDR or http://10.0.4.20).")
    parser.add_argument("--token", default=None, help="Bearer token (overrides env).")
    parser.add_argument("--lan-token-env", default="BUSY_LAN_TOKEN", help="Env var for LAN token (x-api-token).")
    parser.add_argument("--cloud-token-env", default="BUSY_CLOUD_TOKEN", help="Env var for cloud bearer token.")
    parser.add_argument("--assets-dir", default=None, help="Local assets dir (defaults to BUSYBAR_ASSETS_DIR or assets).")
    parser.add_argument("--app-id", default=None, help="App ID (defaults to BUSYBAR_APP_ID or busylib-demo).")
    args = parser.parse_args()

    import os

    addr = args.addr or os.getenv("BUSYBAR_ADDR", "http://10.0.4.20")
    lan_token = os.getenv(args.lan_token_env)
    cloud_token = os.getenv(args.cloud_token_env)
    token = args.token or cloud_token  # used for Authorization
    assets_dir = args.assets_dir or os.getenv("BUSYBAR_ASSETS_DIR", "assets")
    app_id = args.app_id or os.getenv("BUSYBAR_APP_ID", "busylib-demo")

    with BusyBar(addr=addr, token=token) as client:
        if lan_token and not token:
            client.client.headers["x-api-token"] = lan_token
        sync_assets(client, app_id, assets_dir)


if __name__ == "__main__":
    main()
