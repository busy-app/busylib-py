from __future__ import annotations

import os
import argparse
import asyncio
import base64
import binascii
import logging
import shutil
import time
import ipaddress
from urllib.parse import urlparse, urlunparse

from . import display
from .client import AsyncBusyBar
from .keymap import KeyMap, load_keymap, StdinReader, KeyDecoder
from .types import InputKey

PIXEL_CHAR = "⬤"
logger = logging.getLogger(__name__)


def _normalize_http_base(addr: str) -> str:
    return addr if addr.startswith(("http://", "https://")) else f"http://{addr}"


def _http_to_ws(addr: str) -> str:
    parsed = urlparse(addr if "://" in addr else f"http://{addr}")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse(parsed._replace(scheme=scheme))


def _coerce_frame_bytes(message: object) -> bytes | None:
    if isinstance(message, str):
        try:
            return base64.b64decode(message, validate=True)
        except binascii.Error:
            return None
    if isinstance(message, (bytes, bytearray, memoryview)):
        return bytes(message)
    return None


def _rle_decode(data: bytes, blk_size: int) -> bytes | None:
    """
    Decode RLE stream:
    - ctrlByte with high bit set -> copy next (ctrl & 0x7F) blocks as-is.
    - ctrlByte without high bit -> repeat following block ctrl times.
    """
    out = bytearray()
    i = 0
    total = len(data)
    while i < total:
        ctrl = data[i]
        i += 1
        if ctrl & 0x80:
            count = ctrl & 0x7F  # unique blocks, raw count
            need = count * blk_size
            if i + need > total:
                logger.debug("RLE unique block truncated at offset %s", i - 1)
                return None
            out.extend(data[i : i + need])
            i += need
        else:
            count = ctrl  # repeat blocks: count copies of next block
            if i + blk_size > total:
                logger.debug("RLE repeat block missing payload at offset %s", i - 1)
                return None
            block = data[i : i + blk_size]
            i += blk_size
            out.extend(block * count)
    return bytes(out)


def _back_b4_to_b8(data: bytes) -> bytes:
    """
    Convert packed L4 (two pixels per byte) to unpacked 4-bit values.
    """
    out = bytearray(len(data) * 2)
    idx = 0
    for byte in data:
        px1 = byte & 0x0F
        px2 = (byte >> 4) & 0x0F
        out[idx] = px1
        out[idx + 1] = px2
        idx += 2
    return bytes(out)


def _normalize_frame_bytes(data: bytes, width: int, height: int, *, is_back: bool) -> bytes | None:
    expected = width * height * 3
    nibble_expected = (width * height) // 2
    gray_expected = width * height

    # If already RGB sized, accept immediately to avoid double decoding.
    if len(data) == expected:
        logger.debug("Frame accepted as raw RGB len=%s", len(data))
        return data

    if is_back:
        decoded_rle = _rle_decode(data, 2)
        if decoded_rle:
            logger.debug("Frame RLE decoded back display len=%s -> %s", len(data), len(decoded_rle))
            data = decoded_rle

        if len(data) == nibble_expected:
            logger.debug("Frame back L4 packed len=%s; unpacking", len(data))
            unpacked = _back_b4_to_b8(data)
            return b"".join(bytes((v * 17, v * 17, v * 17)) for v in unpacked)
        if len(data) == gray_expected:
            logger.debug("Frame back grayscale len=%s; expanding", len(data))
            return b"".join(bytes((v * 17, v * 17, v * 17)) for v in data)
        if len(data) == expected:
            logger.debug("Frame back already RGB len=%s", len(data))
            return data
    else:
        decoded_rle = _rle_decode(data, 3)
        if decoded_rle:
            logger.debug("Frame RLE decoded front display len=%s -> %s", len(data), len(decoded_rle))
            data = decoded_rle
        if len(data) == expected:
            logger.debug("Frame accepted as raw BGR len=%s", len(data))
            return data
        if len(data) == gray_expected:
            logger.debug("Frame grayscale len=%s; expanding", len(data))
            return b"".join(bytes((v, v, v)) for v in data)

    # Fallback: unsupported size/format.
    logger.warning(
        "Skipping frame: size %s does not match expected %s (or %s L4)",
        len(data),
        expected,
        nibble_expected,
    )
    return None


def render_frame(
    bgr_bytes: bytes,
    width: int,
    height: int,
    spacer: str,
    pixel_char: str,
) -> str:
    lines: list[str] = []
    spacer_str = spacer or ""
    for y in range(height):
        row_parts: list[str] = []
        for x in range(width):
            idx = (y * width + x) * 3
            b, g, r = bgr_bytes[idx : idx + 3]
            if b == g == r == 0:
                cell = " "
            else:
                cell = f"\x1b[38;2;{r};{g};{b}m{pixel_char}\x1b[0m"
            row_parts.append(cell)

        row_str = spacer_str.join(row_parts)
        lines.append(row_str)

    return "\n".join(lines)


async def _forward_keys(
    client: AsyncBusyBar,
    keymap: KeyMap,
    stop_event: asyncio.Event,
    switch_event: asyncio.Event | None = None,
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
            for raw_seq, key_event in decoder.feed(chunk):
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
    base_addr = _normalize_http_base(addr)
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


def _required_size(spec: display.DisplaySpec, spacer: str, pixel_char: str) -> tuple[int, int]:
    cell_width = len(pixel_char) + len(spacer)
    required_cols = spec.width * cell_width - len(spacer)
    required_rows = spec.height
    return required_cols, required_rows


def _compute_terminal_fit(spec: display.DisplaySpec, spacer: str, pixel_char: str) -> tuple[bool, int, int, int, int]:
    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    required_cols, required_rows = _required_size(spec, spacer, pixel_char)
    fits = cols >= required_cols and rows >= required_rows
    return fits, cols, rows, required_cols, required_rows


def _render_size_warning(
    cols: int,
    rows: int,
    required_cols: int,
    required_rows: int,
    spacer: str,
    alt_required: dict[str, tuple[int, int]] | None,
    switch_hint: str,
) -> str:
    line1 = f" Terminal {cols}x{rows} too small; need {required_cols}x{required_rows} "
    extra: list[str] = []
    if spacer:
        extra.append(' Try --spacer "" for compact output ')
    if alt_required:
        front_req = alt_required.get("front")
        back_req = alt_required.get("back")
        if front_req and back_req:
            extra.append(f" Front needs {front_req[0]}x{front_req[1]}; Back needs {back_req[0]}x{back_req[1]} ")
    extra.append(f" Switch display: {switch_hint} ")
    content_lines = [line1] + extra
    inner_width = max(max(len(line) for line in content_lines), 10)
    horizontal = "+" + "-" * inner_width + "+"
    padded_lines = ["|" + line.ljust(inner_width) + "|" for line in content_lines]
    block_lines = [horizontal, *padded_lines, horizontal]
    top_pad = max(0, (rows - len(block_lines)) // 2)
    left_pad = max(0, (cols - len(horizontal)) // 2)
    block = "\n".join(" " * left_pad + line for line in block_lines)
    return ("\n" * top_pad) + block


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
        front_req = _required_size(display.FRONT_DISPLAY, spacer, pixel_char)
        back_req = _required_size(display.BACK_DISPLAY, spacer, pixel_char)
        self._alt_required = {"front": front_req, "back": back_req}
        self._update_size(force=True)

    def _update_size(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or now >= self._next_size_check:
            fits, cols, rows, req_cols, req_rows = _compute_terminal_fit(self.spec, self.spacer, self.pixel_char)
            self._size_info = (cols, rows, req_cols, req_rows)
            self._fits = fits
            self._next_size_check = now + 1.0

    def render(self, bgr_bytes: bytes) -> None:
        self._update_size()
        if not self._fits:
            cols, rows, req_cols, req_rows = self._size_info
            warning = _render_size_warning(
                cols,
                rows,
                req_cols,
                req_rows,
                self.spacer,
                self._alt_required,
                "Tab or Ctrl+R",
            )
            print("\x1b[H" + warning, end="", flush=True)
            self._cleared = False
            return

        if not self._cleared:
            print("\x1b[2J", end="")
            self._cleared = True

        frame = render_frame(
            bgr_bytes,
            self.spec.width,
            self.spec.height,
            self.spacer,
            self.pixel_char,
        )
        print("\x1b[H" + frame, end="", flush=True)


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

            normalized = _normalize_frame_bytes(frame_bytes, spec.width, spec.height, is_back=spec.index == 1)
            if not normalized or len(normalized) != expected_len:
                logger.debug("Stream normalized frame invalid len=%s (expected %s)", 0 if not normalized else len(normalized), expected_len)
                continue

            renderer.render(normalized)
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
                normalized = _normalize_frame_bytes(frame_bytes, spec.width, spec.height, is_back=spec.index == 1)
                if not normalized:
                    logger.debug("Frame normalization failed (len=%s)", len(frame_bytes))
                    await asyncio.sleep(interval)
                    continue
                if len(normalized) != expected_len:
                    logger.debug("Normalized frame len=%s (expected %s)", len(normalized), expected_len)
                    await asyncio.sleep(interval)
                    continue

                renderer.render(normalized)
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
