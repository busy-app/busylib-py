from __future__ import annotations

import argparse
import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from busylib import display, exceptions
from busylib.client import AsyncBusyBar
from examples.remote.keymap import KeyDecoder, KeyMap, StdinReader, load_keymap
from examples.remote.command_core import CommandInput, CommandRegistry, register_command
from examples.remote.commands import InputCapture, discover_commands
from examples.remote.commands.call import build_call_handler
from examples.remote.constants import (
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
from .periodic_tasks import build_periodic_tasks, cloud_link, dashboard, update_check
from .renderers import TerminalRenderer
from .settings import settings

logger = logging.getLogger(__name__)


PERIODIC_TASKS: dict[
    str,
    tuple[Callable[[AsyncBusyBar, TerminalRenderer], Awaitable[None]], float],
] = {
    "info_update": (dashboard, 1),
    "link_check": (cloud_link, 10),
    "update_check": (update_check, 3600),
    # "usb_check": (usb, 5),
}


def _filter_kwargs(
    func: Callable[..., object],
    kwargs: dict[str, object],
) -> dict[str, object]:
    """
    Filter keyword arguments to only those accepted by the target callable.

    This keeps monkeypatched or legacy helpers compatible with newer call sites.
    """
    accepted = set(inspect.signature(func).parameters)
    return {key: value for key, value in kwargs.items() if key in accepted}


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
    client = AsyncBusyBar(addr=addr, token=token_arg)
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


async def _forward_keys(
    client: AsyncBusyBar,
    keymap: KeyMap,
    stop_event: asyncio.Event,
    status_message: Callable[[str], None] | None = None,
    command_queue: asyncio.Queue[Callable[[], Awaitable[None]]] | None = None,
    renderer: TerminalRenderer | None = None,
    on_switch: Callable[[], None] | None = None,
    command_registry: CommandRegistry | None = None,
    command_input: CommandInput | None = None,
    input_capture: InputCapture | None = None,
) -> None:
    """
    Forward terminal key presses to the Busy Bar input API.

    Handles help overlay toggle and quit hotkeys.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    reader = StdinReader(loop, queue)
    decoder = KeyDecoder(keymap)
    command_active = False
    command_buffer = ""
    command_input = command_input or CommandInput()
    reader.start()
    try:
        while not stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(
                    queue.get(), timeout=settings.key_timeout
                )
            except asyncio.TimeoutError:
                continue
            if input_capture and input_capture.handle(chunk):
                continue
            if not command_active and on_switch and _should_switch_display(chunk):
                on_switch()
                stop_event.set()
                return
            if (
                not command_active
                and renderer
                and any(b in (0x68, 0x48) for b in chunk)
            ):  # h/H for help
                renderer.render_help(keymap)
                continue

            async def handle_key_bytes(data: bytes) -> bool:
                """
                Decode and forward key bytes to the device input API.

                Returns True when a stop request was triggered.
                """
                for raw_seq, key_event in decoder.feed(data):
                    if raw_seq in keymap.exit_sequences:
                        stop_event.set()
                        return True
                    if key_event is None:
                        continue
                    try:
                        await client.send_input_key(key_event)
                    except Exception as exc:  # noqa: BLE001 pragma: no cover - network dependent
                        logger.debug("Failed to send key %s: %s", key_event.value, exc)
                return False

            async def handle_command_bytes(data: bytes) -> None:
                """
                Consume command mode input and dispatch on Enter.

                Supports history navigation and ESC to cancel the prompt.
                """
                nonlocal command_active, command_buffer
                for event, payload in command_input.feed(data):
                    if event == "cancel":
                        command_active = False
                        command_buffer = ""
                        if renderer:
                            renderer.update_command_line(None)
                        continue
                    if event == "submit":
                        line = (payload or "").strip()
                        command_active = False
                        command_buffer = ""
                        command_input.begin()
                        if renderer:
                            renderer.update_command_line(None)
                        if line and command_queue and command_registry:
                            await command_queue.put(
                                lambda line=line: _handle_command_line(
                                    line,
                                    command_registry=command_registry,
                                    status_message=status_message,
                                )
                            )
                        continue
                    if event == "update":
                        if isinstance(payload, tuple):
                            command_buffer, command_cursor = payload
                        else:
                            command_buffer = payload or ""
                            command_cursor = len(command_buffer)
                        if renderer:
                            renderer.update_command_line(
                                command_buffer, cursor=command_cursor
                            )

            if command_active:
                await handle_command_bytes(chunk)
                continue

            if b":" in chunk:
                before, _sep, after = chunk.partition(b":")
                if before:
                    should_stop = await handle_key_bytes(before)
                    if should_stop:
                        return
                command_active = True
                command_buffer = ""
                command_input.begin()
                if renderer:
                    renderer.update_command_line("", cursor=0)
                if after:
                    await handle_command_bytes(after)
                continue

            should_stop = await handle_key_bytes(chunk)
            if should_stop:
                return
    finally:
        reader.stop()


async def _handle_command_line(
    line: str,
    *,
    command_registry: CommandRegistry,
    status_message: Callable[[str], None] | None = None,
) -> None:
    """
    Execute a command line with error handling.
    """
    try:
        handled, error = await command_registry.handle(line)
        if not handled and status_message:
            message = error or "Unknown command"
            status_message(f"command: {message}")
    except exceptions.BusyBarAPIError as exc:
        if exc.code == 423:
            message = f"{exc.error} (code: {exc.code})"
            logger.info("Command blocked: %s", message)
            if status_message:
                status_message(message)
            return
        logger.warning("Command failed: %s", exc)
        if status_message:
            status_message(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Command failed")
        if status_message:
            status_message(str(exc))


async def _run_command_queue(
    queue: asyncio.Queue[Callable[[], Awaitable[None]]],
    *,
    stop_event: asyncio.Event,
) -> None:
    """
    Process queued command lines without blocking the frame loop.
    """
    while True:
        if stop_event.is_set() and queue.empty():
            return
        try:
            task = await asyncio.wait_for(queue.get(), timeout=0.05)
        except asyncio.TimeoutError:
            continue
        await task()


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
    command_input = CommandInput()
    input_capture = InputCapture()

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
            renderer: TerminalRenderer | None = None

            def _emit_status(message: str) -> None:
                """
                Emit a status message and mirror it in the renderer footer.
                """
                status_message(message)
                if renderer is not None:
                    renderer.update_status_line(message)

            _emit_status(TEXT_INIT_START)
            client = _build_client(args.addr, args.token)
            base_url = getattr(client, "base_url", None) or args.addr or "unknown"
            status_message(TEXT_INIT_CONNECTING.format(addr=base_url))
            command_registry = CommandRegistry()
            for command in discover_commands(
                client=client,
                status_message=_emit_status,
                stop_event=stop_event,
                input_capture=input_capture,
            ):
                register_command(command_registry, command)
            register_command(
                command_registry,
                "call",
                build_call_handler(client, _emit_status),
            )
            register_command(
                command_registry,
                "api",
                build_call_handler(client, _emit_status),
            )
            command_queue: asyncio.Queue[Callable[[], Awaitable[None]]] = (
                asyncio.Queue()
            )
            renderer = TerminalRenderer(
                spec,
                args.spacer,
                getattr(args, "pixel_char", settings.pixel_char),
                icons,
                frame_mode=getattr(args, "frame", settings.frame_mode),
                frame_color=getattr(args, "frame_color", settings.frame_color),
                clear_screen=clear_screen,
            )
            poll_interval = args.http_poll_interval
            if getattr(client, "is_cloud", False):
                if poll_interval is None or poll_interval < 1.0:
                    poll_interval = 1.0
            parsed_addr = urlparse(base_url)
            if poll_interval is not None and poll_interval > 0:
                protocol = parsed_addr.scheme or "http"
            else:
                protocol = "wss" if parsed_addr.scheme == "https" else "ws"
            renderer.update_info(
                streaming_info=_format_streaming_info(base_url, protocol)
            )
            info_stop = asyncio.Event()

            tasks: list[asyncio.Task] = []
            if keymap:
                forward_kwargs = _filter_kwargs(
                    _forward_keys,
                    {
                        "client": client,
                        "keymap": keymap,
                        "stop_event": stop_event,
                        "status_message": status_message,
                        "command_queue": command_queue,
                        "renderer": renderer,
                        "on_switch": _switch_display,
                        "command_registry": command_registry,
                        "command_input": command_input,
                    },
                )
                tasks.append(asyncio.create_task(_forward_keys(**forward_kwargs)))
            tasks.append(
                asyncio.create_task(
                    _run_command_queue(
                        command_queue,
                        stop_event=stop_event,
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
                            await command_queue.put(lambda task=task: task())
                            last_run[name] = now

                    await asyncio.sleep(settings.frame_sleep)

            tasks.append(asyncio.create_task(_periodic_loop()))

            if poll_interval is not None and poll_interval > 0:
                logger.info(
                    TEXT_HTTP_POLL.format(
                        interval=poll_interval,
                        addr=base_url,
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
                            status_message=_emit_status,
                        )
                    )
                )
            else:
                logger.info(TEXT_WS_STREAM.format(addr=base_url))
                tasks.append(
                    asyncio.create_task(
                        _stream_ws(
                            client=client,
                            spec=spec,
                            stop_event=stop_event,
                            renderer=renderer,
                            status_message=_emit_status,
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
