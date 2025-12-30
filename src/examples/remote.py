from __future__ import annotations

import os
import argparse
import asyncio
import logging
import re
import shutil
import time
import ipaddress
from urllib.parse import urlparse
import re

from busylib import display
from busylib.client import AsyncBusyBar
from busylib.keymap import KeyMap, load_keymap, StdinReader, KeyDecoder

PIXEL_CHAR = "⬤"
logger = logging.getLogger(__name__)


async def _forward_keys(
    client: AsyncBusyBar,
    keymap: KeyMap,
    stop_event: asyncio.Event,
    switch_event: asyncio.Event | None = None,
    renderer: "TerminalRenderer | None" = None,
) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    reader = StdinReader(loop, queue)
    decoder = KeyDecoder(keymap)
    reader.start()
    try:
        while not stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            if switch_event is not None and any(b in (0x09, 0x12) for b in chunk):
                switch_event.set()
                stop_event.set()
                continue
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


def _build_client(addr: str, token_arg: str | None) -> AsyncBusyBar:
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
            lan_token = os.getenv("BUSY_LAN_TOKEN")
            if lan_token:
                extra_headers["x-api-token"] = lan_token
        if not extra_headers:
            cloud_token = os.getenv("BUSY_CLOUD_TOKEN")
            if cloud_token:
                token = cloud_token

    client = AsyncBusyBar(addr=base_addr, token=token)
    if extra_headers:
        client.client.headers.update(extra_headers)
    return client


class TerminalRenderer:
    """
    Terminal rendering with periodic size checks and warnings.
    """

    def __init__(self, spec: display.DisplaySpec, spacer: str, pixel_char: str) -> None:
        self.spec = spec
        self.spacer = spacer
        self.pixel_char = pixel_char
        self._next_size_check = 0.0
        self._fits = True
        self._size_info: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._cleared = False
        front_req = self._required_size(display.FRONT_DISPLAY)
        back_req = self._required_size(display.BACK_DISPLAY)
        self._alt_required = {"front": front_req, "back": back_req}
        self._update_size(force=True)
        self._help_active = False
        self._help_keymap: KeyMap | None = None

    def _update_size(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or now >= self._next_size_check:
            cols, rows = shutil.get_terminal_size(fallback=(80, 24))
            req_cols, req_rows = self._required_size(self.spec)
            self._size_info = (cols, rows, req_cols, req_rows)
            self._fits = cols >= req_cols and rows >= req_rows
            self._next_size_check = now + 1.0

    def _required_size(self, spec: display.DisplaySpec) -> tuple[int, int]:
        cell_width = len(self.pixel_char) + len(self.spacer)
        required_cols = spec.width * cell_width - len(self.spacer)
        required_rows = spec.height
        return required_cols, required_rows

    def render(self, bgr_bytes: bytes) -> None:
        """
        Render a single RGB frame to the terminal with size guarding.
        """
        self._update_size()
        if self._help_active:
            self._render_help_frame()
            return
        if not self._fits:
            cols, rows, req_cols, req_rows = self._size_info
            warning = self._render_size_warning(cols, rows, req_cols, req_rows)
            print("\x1b[H" + warning, end="", flush=True)
            self._cleared = False
            return

        if not self._cleared:
            print("\x1b[2J", end="")
            self._cleared = True

        lines: list[str] = []
        spacer_str = self.spacer or ""
        for y in range(self.spec.height):
            row_parts: list[str] = []
            for x in range(self.spec.width):
                idx = (y * self.spec.width + x) * 3
                b, g, r = bgr_bytes[idx : idx + 3]
                if b == g == r == 0:
                    cell = " "
                else:
                    cell = f"\x1b[38;2;{r};{g};{b}m{self.pixel_char}\x1b[0m"
                row_parts.append(cell)
            lines.append(spacer_str.join(row_parts))

        frame = "\n".join(lines)
        print("\x1b[H" + frame, end="", flush=True)

    def _render_size_warning(self, cols: int, rows: int, required_cols: int, required_rows: int) -> str:
        line1 = f" Terminal {cols}x{rows} too small; need {required_cols}x{required_rows} "
        extra: list[str] = []
        if self.spacer:
            extra.append(' Try --spacer "" for compact output ')
        front_req = self._alt_required.get("front")
        back_req = self._alt_required.get("back")
        if front_req and back_req:
            extra.append(f" Front needs {front_req[0]}x{front_req[1]}; Back needs {back_req[0]}x{back_req[1]} ")
        extra.append(" Quit: Ctrl+Q | Help: h | Switch: Tab or Ctrl+R ")
        return self._boxed([line1] + extra, top_pad_rows=rows, padding=2)

    def render_help(self, keymap: KeyMap | None) -> None:
        """
        Toggle a brief help overlay. When active, frames are paused.
        """
        if self._help_active:
            self._hide_help()
            return
        self._show_help(keymap)

    def _render_help_frame(self) -> None:
        cols, _rows = shutil.get_terminal_size(fallback=(80, 24))
        program_actions: dict[str, list[str]] = {
            "Switch display": ["Tab", "Ctrl+R"],
            "Quit": ["Ctrl+Q"],
            "Help toggle": ["h"],
        }

        bar_actions: dict[str, list[str]] = {}
        if self._help_keymap:
            for seq, label in self._help_keymap.labels.items():
                mapped = self._help_keymap.mapping.get(seq)
                if not mapped:
                    continue
                if "ss3" in label:
                    continue
                bar_actions.setdefault(mapped.value, []).append(label)

        bold = "\x1b[1m"
        reset = "\x1b[0m"

        def format_group(title: str, actions: dict[str, list[str]]) -> list[str]:
            lines: list[str] = [f"{bold}{title}:{reset}"]
            for action, keys in actions.items():
                combo = "/".join(sorted(set(keys), key=str.lower))
                lines.append(f"  {bold}{combo}{reset} {action}")
            return lines

        lines: list[str] = []
        lines.extend(format_group("Program", program_actions))
        if bar_actions:
            lines.append("")  # spacer
            lines.extend(format_group("Bar", bar_actions))

        # compute column widths ignoring ANSI
        visible = [self._visible_len(l) for l in lines]
        col_count = 3 if cols >= 60 else 2
        widths = [0] * col_count
        formatted_rows: list[str] = []
        row_items: list[str] = []
        max_width = max(10, min(cols - 4, max(visible) if visible else 10))
        for text, vis_len in zip(lines, visible):
            if not text:  # spacer forces new row
                if row_items:
                    padded = [
                        t + " " * (widths[i] - self._visible_len(t))
                        for i, t in enumerate(row_items)
                    ]
                    formatted_rows.append("  ".join(padded))
                    row_items = []
                    widths = [0] * col_count
                formatted_rows.append("")
                continue

            # truncate long lines to fit the terminal width
            if vis_len > max_width:
                plain = self._strip_ansi(text)
                trimmed = plain[: max(0, max_width - 3)] + "..."
                text = trimmed
                vis_len = len(trimmed)

            idx = len(row_items)
            widths[idx % col_count] = max(widths[idx % col_count], vis_len)
            row_items.append(text)
            if len(row_items) == col_count:
                padded = [
                    t + " " * (widths[i] - self._visible_len(t))
                    for i, t in enumerate(row_items)
                ]
                formatted_rows.append("  ".join(padded))
                row_items = []
                widths = [0] * col_count

        if row_items:
            padded = [
                t + " " * (widths[i] - self._visible_len(t))
                for i, t in enumerate(row_items)
            ]
            formatted_rows.append("  ".join(padded))

        print("\x1b[2J\x1b[H" + self._boxed(formatted_rows, padding=2), end="", flush=True)
        self._cleared = False

    def _show_help(self, keymap: KeyMap | None) -> None:
        self._help_active = True
        self._help_keymap = keymap
        self._render_help_frame()

    def _hide_help(self) -> None:
        self._help_active = False
        self._help_keymap = None
        print("\x1b[2J", end="")
        self._cleared = False

    def _boxed(self, lines: list[str], top_pad_rows: int | None = None, padding: int = 0) -> str:
        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        stripped = [self._strip_ansi(line) for line in lines]
        max_width = max(10, min(cols - 4 - padding * 2, max(len(line) for line in stripped) if stripped else 10))
        inner_width = max_width
        horizontal = "+" + "-" * (inner_width + padding * 2) + "+"
        padded_lines = []
        for raw, plain in zip(lines, stripped):
            text = plain
            if len(text) > max_width:
                text = text[: max(0, max_width - 3)] + "..."
            pad_len = inner_width - len(text)
            padded_lines.append("|" + " " * padding + raw + " " * pad_len + " " * padding + "|")
        block_lines = [horizontal, *padded_lines, horizontal]
        block_height = len(block_lines)
        top_pad = top_pad_rows if top_pad_rows is not None else rows
        top_pad = max(0, (top_pad - block_height) // 2)
        left_pad = max(0, (cols - len(horizontal)) // 2)
        block = "\n".join(" " * left_pad + line for line in block_lines)
        return ("\n" * top_pad) + block

    @staticmethod
    def _visible_len(text: str) -> int:
        return len(TerminalRenderer._strip_ansi(text))

    @staticmethod
    def _strip_ansi(text: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*m", "", text)


async def _stream_ws(
    client: AsyncBusyBar,
    display_index: int,
    spec: display.DisplaySpec,
    stop_event: asyncio.Event,
    renderer: "TerminalRenderer",
) -> None:
    base_addr = client.base_url
    expected_len = spec.width * spec.height * 3

    logger.info("Streaming via WebSocket from %s/api/screen/ws (display=%s)", base_addr, display_index)
    try:
        async for frame_bytes in client.stream_screen_ws(display_index):
            if stop_event.is_set():
                break
            if not frame_bytes:
                logger.debug("Stream frame empty; skipping")
                continue

            if len(frame_bytes) != expected_len:
                logger.debug("Stream frame len=%s (expected %s)", len(frame_bytes), expected_len)
            renderer.render(frame_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("WebSocket stream error: %s", exc)
    finally:
        await client.aclose()
        stop_event.set()


async def _poll_http(
    client: AsyncBusyBar,
    display_index: int,
    spec: display.DisplaySpec,
    interval: float,
    stop_event: asyncio.Event,
    renderer: "TerminalRenderer",
) -> None:
    expected_len = spec.width * spec.height * 3
    base_addr = client.base_url

    print("\x1b[2J", end="")
    try:
        while not stop_event.is_set():
            try:
                frame_bytes = await client.get_screen_frame(display_index)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Polling failed: %s", exc)
                await asyncio.sleep(interval)
                continue

            if frame_bytes:
                if len(frame_bytes) != expected_len:
                    logger.debug("Received frame len=%s (expected %s)", len(frame_bytes), expected_len)
                renderer.render(frame_bytes)
            await asyncio.sleep(interval)
    finally:
        await client.aclose()
        stop_event.set()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream screen to console.")
    parser.add_argument("--addr", default="http://10.0.4.20", help="Device address.")
    parser.add_argument("--display", type=int, default=0, help="Display index (default: 0).")
    parser.add_argument("--token", default=None, help="Bearer token.")
    parser.add_argument(
        "--http-poll-interval",
        type=float,
        default=0.0,
        help="Poll /api/screen over HTTP instead of websocket; seconds between polls (0 to disable).",
    )
    parser.add_argument(
        "--spacer",
        type=str,
        default=" ",
        help="String inserted between pixels.",
    )
    parser.add_argument(
        "--pixel-char",
        type=str,
        default=PIXEL_CHAR,
        help="Symbol to render pixels (default: ⬤).",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--log-file", default="screen.log", help="Log file path.")
    parser.add_argument(
        "--no-send-input",
        action="store_true",
        help="Disable forwarding terminal keys to /api/input.",
    )
    parser.add_argument(
        "--keymap-file",
        type=str,
        default=None,
        help="Optional JSON keymap file.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Silence console logs (file logging remains).",
    )
    return parser.parse_args()


def _setup_logging(*, level: str, log_file: str, quiet: bool) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger_root = logging.getLogger()
    logger_root.handlers.clear()
    logger_root.setLevel(numeric_level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger_root.addHandler(file_handler)
    if not quiet:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(numeric_level)
        stream_handler.setFormatter(fmt)
        logger_root.addHandler(stream_handler)


async def _run(args: argparse.Namespace) -> None:
    _setup_logging(level=args.log_level, log_file=args.log_file, quiet=args.quiet)

    current_display = args.display
    keymap = load_keymap(args.keymap_file) if not args.no_send_input else None

    print("\x1b[2J", end="")
    while True:
        spec = display.get_display_spec(current_display)
        stop_event = asyncio.Event()
        switch_event = asyncio.Event()
        client = _build_client(args.addr, args.token)
        renderer = TerminalRenderer(spec, args.spacer, args.pixel_char)

        tasks: list[asyncio.Task] = []
        if keymap:
            tasks.append(
                asyncio.create_task(
                    _forward_keys(
                        client=client,
                        keymap=keymap,
                        stop_event=stop_event,
                        switch_event=switch_event,
                        renderer=renderer,
                    )
                )
            )

        if args.http_poll_interval and args.http_poll_interval > 0:
            logger.info("Polling /api/screen every %ss from %s (display=%s)", args.http_poll_interval, args.addr, current_display)
            tasks.append(
                asyncio.create_task(
                    _poll_http(
                        client=client,
                        display_index=current_display,
                        spec=spec,
                        interval=args.http_poll_interval,
                        stop_event=stop_event,
                        renderer=renderer,
                    )
                )
            )
        else:
            logger.info("Streaming screen from %s (display=%s)", args.addr, current_display)
            tasks.append(
                asyncio.create_task(
                    _stream_ws(
                        client=client,
                        display_index=current_display,
                        spec=spec,
                        stop_event=stop_event,
                        renderer=renderer,
                    )
                )
            )

        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            stop_event.set()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.gather(*done, return_exceptions=True)
        except KeyboardInterrupt:
            stop_event.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            print("\nStopped.")
            break
        finally:
            await client.aclose()

        if switch_event.is_set():
            current_display = 1 if current_display == 0 else 0
            logger.info("Switching to display %s", current_display)
            print("\x1b[2J", end="")  # clear terminal
            continue
        break


def main() -> None:
    args = parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
