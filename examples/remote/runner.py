from __future__ import annotations

import argparse
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from busylib import display
from busylib.client import AsyncBusyBar
from busylib.keymap import KeyDecoder, KeyMap, StdinReader, load_keymap
from busylib.settings import settings

from .constants import (
    DEFAULT_FRAME_SLEEP,
    DEFAULT_KEY_TIMEOUT,
    SWITCH_DISPLAY_SEQUENCES,
    TEXT_HTTP_POLL,
    TEXT_INIT_CONNECTING,
    TEXT_INIT_HTTP,
    TEXT_INIT_START,
    TEXT_INIT_STREAMING,
    TEXT_INIT_WAIT_FRAME,
    TEXT_INIT_WS,
    TEXT_POLL_FAIL,
    TEXT_POLL_LEN,
    TEXT_STOPPED,
    TEXT_STREAM_EMPTY,
    TEXT_STREAM_LEN,
    TEXT_STREAMING_INFO,
    TEXT_WS_STREAM,
    TEXT_WS_STREAM_VERBOSE,
)
from .periodic_tasks import build_periodic_tasks, dashboard
from .renderers import TerminalRenderer

logger = logging.getLogger(__name__)


PERIODIC_TASKS: dict[
    str,
    tuple[Callable[[AsyncBusyBar, TerminalRenderer], Awaitable[None]], float],
] = {
    "info_update": (dashboard, 1),
    # "usb_check": (usb, 5),
}


def _should_switch_display(chunk: bytes) -> bool:
    """
    Check whether the input chunk requests a display switch.
    """
    return any(seq in chunk for seq in SWITCH_DISPLAY_SEQUENCES)


def _build_client(addr: str, token_arg: str | None) -> AsyncBusyBar:
    """
    Build an AsyncBusyBar client with LAN/cloud token handling.

    This keeps address normalization and header logic in one place.
    """
    base_addr = addr if addr.startswith(("http://", "https://")) else f"http://{addr}"
    parsed = urlparse(base_addr)
    host = parsed.hostname or ""
    token = token_arg

    cloud = token is not None and _is_cloud_addr(base_addr)
    if cloud and "://" not in addr:
        client_addr = settings.cloud_base_url
    else:
        client_addr = base_addr if cloud else host
    client = AsyncBusyBar(addr=client_addr, token=token, cloud=cloud)
    return client


def _format_streaming_info(addr: str, protocol: str) -> str:
    """
    Build streaming info with protocol and host address.

    The address is normalized to include the host and port if provided.
    """
    base_addr = addr if "://" in addr else f"http://{addr}"
    parsed = urlparse(base_addr)
    host = parsed.hostname or addr
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return TEXT_STREAMING_INFO.format(protocol=protocol, host=host)


def _is_cloud_addr(addr: str) -> bool:
    """
    Decide whether the address matches the configured cloud proxy.

    The match compares hostnames and honors explicit ports.
    """
    base_addr = addr if "://" in addr else f"http://{addr}"
    cloud_addr = settings.cloud_base_url
    parsed = urlparse(base_addr)
    cloud_parsed = urlparse(cloud_addr)
    if parsed.hostname and cloud_parsed.hostname:
        if parsed.hostname != cloud_parsed.hostname:
            return False
        if cloud_parsed.port is not None and parsed.port != cloud_parsed.port:
            return False
        return True
    return base_addr.rstrip("/") == cloud_addr.rstrip("/")


async def _forward_keys(
    client: AsyncBusyBar,
    keymap: KeyMap,
    stop_event: asyncio.Event,
    renderer: TerminalRenderer | None = None,
    on_switch: Callable[[], None] | None = None,
) -> None:
    """
    Forward terminal key presses to the Busy Bar input API.

    Handles help overlay toggle and quit hotkeys.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    reader = StdinReader(loop, queue)
    decoder = KeyDecoder(keymap)
    reader.start()
    try:
        while not stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=DEFAULT_KEY_TIMEOUT)
            except asyncio.TimeoutError:
                continue
            if on_switch and _should_switch_display(chunk):
                on_switch()
                stop_event.set()
                return
            if renderer and any(b in (0x68, 0x48) for b in chunk):  # h/H for help
                renderer.render_help(keymap)
                continue
            for raw_seq, key_event in decoder.feed(chunk):
                # help already handled above; decoder-only path not needed
                if raw_seq in keymap.exit_sequences:
                    stop_event.set()
                    return
                if key_event is None:
                    continue
                try:
                    await client.send_input_key(key_event)
                except Exception as exc:  # noqa: BLE001 pragma: no cover - network dependent
                    logger.debug("Failed to send key %s: %s", key_event.value, exc)
    finally:
        reader.stop()


async def _stream_ws(
    client: AsyncBusyBar,
    spec: display.DisplaySpec,
    stop_event: asyncio.Event,
    renderer: TerminalRenderer,
    status_message: Callable[[str], None],
) -> None:
    """
    Stream screen frames over WebSocket and render them.

    Exceptions are re-raised so the caller can report failures.
    """
    base_addr = client.base_url
    expected_len = spec.width * spec.height * 3

    logger.info(TEXT_WS_STREAM_VERBOSE.format(base=base_addr))
    status_message(TEXT_INIT_WS)
    status_message(TEXT_INIT_WAIT_FRAME)
    first_frame = True
    try:
        # stream_screen_ws yields bytes | str
        async for message in client.stream_screen_ws(spec):
            if stop_event.is_set():
                break
            if not message:
                logger.debug(TEXT_STREAM_EMPTY)
                continue

            if isinstance(message, str):
                logger.debug("Server message: %s", message)
                continue
            if first_frame:
                status_message(TEXT_INIT_STREAMING)
                first_frame = False

            if len(message) != expected_len:
                logger.debug(
                    TEXT_STREAM_LEN.format(
                        size=len(message),
                        expected=expected_len,
                    )
                )
            renderer.render(message)
    except Exception as exc:  # noqa: BLE001
        logger.warning("WebSocket stream error: %s", exc)
        raise
    finally:
        await client.aclose()
        stop_event.set()


async def _poll_http(
    client: AsyncBusyBar,
    spec: display.DisplaySpec,
    interval: float,
    stop_event: asyncio.Event,
    renderer: TerminalRenderer,
    clear_screen: Callable[[str], None],
    status_message: Callable[[str], None],
) -> None:
    """
    Poll /api/screen over HTTP and render frames.

    The terminal is cleared on the first received frame only.
    """
    expected_len = spec.width * spec.height * 3
    cleared = False
    status_message(TEXT_INIT_HTTP)
    status_message(TEXT_INIT_WAIT_FRAME)
    try:
        while not stop_event.is_set():
            try:
                frame_bytes = await client.get_screen_frame(spec)
            except Exception as exc:  # noqa: BLE001
                logger.warning(TEXT_POLL_FAIL, exc)
                await asyncio.sleep(interval)
                continue

            if frame_bytes:
                if not cleared:
                    status_message(TEXT_INIT_STREAMING)
                    clear_screen("http_poll_first_frame")
                    cleared = True
                if len(frame_bytes) != expected_len:
                    logger.debug(
                        TEXT_POLL_LEN.format(
                            size=len(frame_bytes),
                            expected=expected_len,
                        )
                    )
                renderer.render(frame_bytes)
            await asyncio.sleep(interval)
    finally:
        await client.aclose()
        stop_event.set()


async def _run(
    args: argparse.Namespace,
    *,
    icons: dict[str, str],
    clear_screen: Callable[[str], None],
    clear_terminal: Callable[[], None],
    status_message: Callable[[str], None],
) -> None:
    """
    Run the remote streaming loop with keyboard forwarding and status updates.

    This manages streaming tasks and periodic polling.
    """
    current_display = display.FRONT_DISPLAY
    keymap = load_keymap(args.keymap_file) if not args.no_send_input else None

    had_error = False
    try:
        while True:
            switch_requested = False

            def _switch_display() -> None:
                """
                Toggle between front and back displays.
                """
                nonlocal current_display, switch_requested
                switch_requested = True
                current_display = (
                    display.BACK_DISPLAY
                    if current_display == display.FRONT_DISPLAY
                    else display.FRONT_DISPLAY
                )

            spec = display.get_display_spec(current_display)
            stop_event = asyncio.Event()
            status_message(TEXT_INIT_START)
            status_message(TEXT_INIT_CONNECTING.format(addr=args.addr))
            client = _build_client(args.addr, args.token)
            renderer = TerminalRenderer(
                spec,
                args.spacer,
                args.pixel_char,
                icons,
                clear_screen=clear_screen,
            )
            poll_interval = args.http_poll_interval
            if client.is_cloud:
                if poll_interval is None or poll_interval < 1.0:
                    poll_interval = 1.0
            parsed_addr = urlparse(
                args.addr if "://" in args.addr else f"http://{args.addr}"
            )
            if poll_interval is not None and poll_interval > 0:
                protocol = parsed_addr.scheme or "http"
            else:
                protocol = "wss" if parsed_addr.scheme == "https" else "ws"
            renderer.update_info(
                streaming_info=_format_streaming_info(args.addr, protocol)
            )
            info_stop = asyncio.Event()

            tasks: list[asyncio.Task] = []
            if keymap:
                tasks.append(
                    asyncio.create_task(
                        _forward_keys(
                            client=client,
                            keymap=keymap,
                            stop_event=stop_event,
                            renderer=renderer,
                            on_switch=_switch_display,
                        )
                    )
                )

            async def _periodic_loop() -> None:
                """
                Periodically refresh device snapshot and USB status.

                Uses the configured intervals to avoid excessive polling.
                """
                task_map = build_periodic_tasks(client, renderer, tasks=PERIODIC_TASKS)
                last_run = {name: 0.0 for name in task_map}

                while not stop_event.is_set() and not info_stop.is_set():
                    now = time.monotonic()

                    for name, (interval, task) in task_map.items():
                        if now - last_run[name] >= interval:
                            await task()
                            last_run[name] = now

                    await asyncio.sleep(DEFAULT_FRAME_SLEEP)

            tasks.append(asyncio.create_task(_periodic_loop()))

            if poll_interval is not None and poll_interval > 0:
                logger.info(
                    TEXT_HTTP_POLL.format(
                        interval=poll_interval,
                        addr=args.addr,
                    )
                )
                tasks.append(
                    asyncio.create_task(
                        _poll_http(
                            client=client,
                            spec=spec,
                            interval=poll_interval,
                            stop_event=stop_event,
                            renderer=renderer,
                            clear_screen=clear_screen,
                            status_message=status_message,
                        )
                    )
                )
            else:
                logger.info(TEXT_WS_STREAM.format(addr=args.addr))
                tasks.append(
                    asyncio.create_task(
                        _stream_ws(
                            client=client,
                            spec=spec,
                            stop_event=stop_event,
                            renderer=renderer,
                            status_message=status_message,
                        )
                    )
                )

            try:
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                stop_event.set()
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                results = await asyncio.gather(*done, return_exceptions=True)
                for result in results:
                    if isinstance(result, asyncio.CancelledError):
                        continue
                    if isinstance(result, BaseException):
                        raise result
            except KeyboardInterrupt:
                stop_event.set()
                info_stop.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                print()
                print(TEXT_STOPPED)
                break
            finally:
                info_stop.set()
                await client.aclose()

            if switch_requested:
                continue

            break
    except BaseException:
        had_error = True
        raise
    finally:
        if not had_error:
            clear_terminal()
