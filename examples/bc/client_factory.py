from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from busylib.client import AsyncBusyBar


def build_client(addr: str, token_arg: str | None) -> AsyncBusyBar:
    """
    Create an AsyncBusyBar client with token resolution.

    Handles LAN tokens for private hosts and cloud tokens as fallback.
    """
    base_addr = addr if addr.startswith(("http://", "https://")) else f"http://{addr}"
    parsed = urlparse(base_addr)
    host = parsed.hostname or ""
    token = token_arg
    extra_headers: dict[str, str] = {}

    if token is None:
        try:
            ip = ipaddress.ip_address(host)
            is_private = ip.is_private
        except ValueError:
            is_private = host.endswith(".local") or host.startswith("localhost")

        if is_private:
            lan_token = os.getenv("BUSYLIB_LAN_TOKEN") or os.getenv("BUSY_LAN_TOKEN")
            if lan_token:
                extra_headers["x-api-token"] = lan_token
        if not extra_headers:
            cloud_token = os.getenv("BUSYLIB_CLOUD_TOKEN") or os.getenv(
                "BUSY_CLOUD_TOKEN"
            )
            if cloud_token:
                token = cloud_token

    client = AsyncBusyBar(addr=base_addr, token=token)
    if extra_headers:
        client.client.headers.update(extra_headers)
    return client
