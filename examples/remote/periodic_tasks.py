from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from busylib.client import AsyncBusyBar
from busylib.features import (
    DeviceSnapshot,
    DeviceStateStore,
    collect_device_snapshot,
)

from examples.remote.constants import (
    TEXT_LINK_FAIL,
    TEXT_SNAPSHOT_FAIL,
    TEXT_UPDATE_FAIL,
)
from examples.remote.renderers import TerminalRenderer

logger = logging.getLogger(__name__)


async def dashboard(client: AsyncBusyBar, renderer: TerminalRenderer) -> None:
    """
    Refresh device snapshot and update the renderer.
    """
    try:
        snapshot = await collect_device_snapshot(client)
        renderer.update_info(snapshot=snapshot)
    except Exception as exc:
        logger.warning(TEXT_SNAPSHOT_FAIL, exc)


async def stream_dashboard_state(
    client: AsyncBusyBar,
    renderer: TerminalRenderer,
    *,
    initial_snapshot: DeviceSnapshot,
) -> None:
    """
    Keep dashboard info in sync from `/api/status/ws` protobuf updates.

    The initial snapshot is collected via HTTP once. After that, only
    websocket state updates are applied.
    """
    store = DeviceStateStore(initial_snapshot)
    store.on_state(lambda snapshot: renderer.update_info(snapshot=snapshot))
    renderer.update_info(snapshot=store.snapshot)
    async for message in client.stream_status_ws():
        if not isinstance(message, dict):
            continue
        store.apply_stream_message(message)


async def cloud_link(client: AsyncBusyBar, renderer: TerminalRenderer) -> None:
    """
    Refresh cloud link status and update the renderer.
    """
    try:
        info = await client.account_info()
        if info.linked:
            renderer.update_info(
                link_connected=True,
                link_key=None,
                link_email=info.email,
            )
            return
        link_info = await client.account_link()
        renderer.update_info(
            link_connected=False,
            link_key=link_info.code,
        )
    except Exception as exc:
        logger.warning(TEXT_LINK_FAIL, exc)


async def update_check(client: AsyncBusyBar, renderer: TerminalRenderer) -> None:
    """
    Request a firmware update check and update the renderer.
    """
    try:
        await client.update_check()
        status = await client.update_status()
        available = False
        if status.check and status.check.available_version:
            available = True
        renderer.update_info(update_available=available)
    except Exception as exc:
        logger.warning(TEXT_UPDATE_FAIL, exc)


def build_periodic_tasks(
    client: AsyncBusyBar,
    renderer: TerminalRenderer,
    tasks: dict[
        str,
        tuple[Callable[[AsyncBusyBar, TerminalRenderer], Awaitable[None]], float],
    ],
) -> dict[str, tuple[float, Callable[[], Awaitable[None]]]]:
    """
    Build periodic tasks with intervals and async callables.

    Each task returns None and handles its own errors.
    """
    return {
        name: (interval, lambda f=func: f(client, renderer))
        for name, (func, interval) in tasks.items()
    }
