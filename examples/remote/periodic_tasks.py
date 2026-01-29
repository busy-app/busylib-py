from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable

from busylib.client import AsyncBusyBar
from busylib.features import collect_device_snapshot

from examples.remote.constants import TEXT_SNAPSHOT_FAIL, TEXT_USB_FAIL
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


async def usb(client: AsyncBusyBar, renderer: TerminalRenderer) -> None:
    """
    Refresh USB status and update the renderer.
    """
    try:
        result = client.usb.discover()
        if inspect.isawaitable(result):
            is_connected = await result
        else:
            is_connected = result
        renderer.update_info(usb_connected=is_connected)
    except Exception as exc:
        logger.warning(TEXT_USB_FAIL, exc)


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
