from __future__ import annotations

import argparse
import asyncio
import curses
import curses.ascii
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from typing import Protocol

import ipaddress
from busylib.client import AsyncBusyBar
from busylib import types


@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int
    path: str | None = None


def human_size(value: int) -> str:
    units = ["B", "K", "M", "G", "T"]
    size = float(value)
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.1f}{units[unit]}" if unit else f"{int(size)}B"


class Panel:
    def __init__(self) -> None:
        self.entries: list[Entry] = []
        self.index = 0

    @property
    def selected(self) -> Entry:
        return self.entries[self.index]

    def move(self, delta: int) -> None:
        self.index = max(0, min(len(self.entries) - 1, self.index + delta))

    def set_index(self, value: int) -> None:
        self.index = max(0, min(len(self.entries) - 1, value))

    def refresh(self) -> None:
        raise NotImplementedError

    def enter(self) -> None:
        raise NotImplementedError

    def path_of(self, entry: Entry) -> str:
        raise NotImplementedError

    def dest_path(self, name: str) -> str:
        raise NotImplementedError

    def build_entry(self, name: str, is_dir: bool, size: int) -> Entry:
        return Entry(name=name, is_dir=is_dir, size=size, path=self.dest_path(name))


class LocalPanel(Panel):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.cwd = root
        self.refresh()

    def refresh(self) -> None:
        items: list[Entry] = [Entry("..", True, 0)]
        for entry in sorted(self.cwd.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            items.append(
                self.build_entry(entry.name, entry.is_dir(), entry.stat().st_size if entry.is_file() else 0)
            )
        if self.cwd == self.root:
            self.entries = items[1:]
        else:
            self.entries = items
        self.set_index(0)

    def enter(self) -> None:
        entry = self.selected
        if not entry.is_dir:
            return
        if entry.name == "..":
            if self.cwd != self.root:
                self.cwd = self.cwd.parent
        else:
            self.cwd = self.cwd / entry.name
        self.refresh()

    def path_of(self, entry: Entry) -> str:
        if entry.name == "..":
            return str(self.cwd.parent if self.cwd != self.root else self.cwd)
        return str(self.cwd / entry.name)

    def dest_path(self, name: str) -> str:
        return str(self.cwd / name)


class RemotePanel(Panel):
    def __init__(self, client: AsyncBusyBar, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.client = client
        self.loop = loop
        self.cwd = "/ext"
        self.error: str | None = None
        self.refresh()

    def refresh(self) -> None:
        try:
            listing = self.loop.run_until_complete(self.client.list_storage_files(self.cwd))
            items: list[Entry] = [Entry("..", True, 0)]
            for element in sorted(listing.list, key=lambda e: (e.type != "dir", e.name.lower())):
                size = getattr(element, "size", 0) if element.type == "file" else 0
                items.append(self.build_entry(element.name, element.type == "dir", size))
            if self.cwd == "/":
                self.entries = items[1:]
            else:
                self.entries = items
            self.error = None
            self.set_index(0)
        except Exception as exc:  # noqa: BLE001
            self.error = f"Remote refresh failed: {exc}"
            self.entries = [Entry("..", True, 0)]
            self.set_index(0)

    def enter(self) -> None:
        entry = self.selected
        if not entry.is_dir:
            return
        if entry.name == "..":
            if self.cwd != "/":
                self.cwd = "/".join(self.cwd.rstrip("/").split("/")[:-1]) or "/"
        else:
            self.cwd = (self.cwd.rstrip("/") + "/" + entry.name).replace("//", "/")
        self.refresh()

    def path_of(self, entry: Entry) -> str:
        if entry.name == "..":
            return self.cwd
        return (self.cwd.rstrip("/") + "/" + entry.name).replace("//", "/")

    def dest_path(self, name: str) -> str:
        return (self.cwd.rstrip("/") + "/" + name).replace("//", "/")


def draw_panel(stdscr: curses.window, panel: Panel, y: int, x: int, width: int, active: bool) -> None:
    def safe_draw(row: int, col: int, text: str, attr: int = curses.A_NORMAL) -> None:
        if row < 0 or row >= curses.LINES or col >= curses.COLS:
            return
        maxw = max(0, min(width, curses.COLS - col))
        if maxw == 0:
            return
        try:
            stdscr.addnstr(row, col, text[:maxw], maxw, attr)
        except curses.error:
            pass

    title_attr = curses.A_REVERSE if active else curses.A_NORMAL
    title = f" {panel.__class__.__name__.replace('Panel','')} "
    safe_draw(y, x, title.ljust(width), title_attr)
    safe_draw(y + 1, x, "─" * width)

    for idx, entry in enumerate(panel.entries):
        line = f"{entry.name}/" if entry.is_dir else entry.name
        size = "" if entry.is_dir else human_size(entry.size)
        row = y + idx + 2
        if row >= curses.LINES - 1:
            break
        attr = curses.A_REVERSE if idx == panel.index and active else curses.A_NORMAL
        name_w = max(0, width - 10)
        safe_draw(row, x, line.ljust(name_w), attr)
        safe_draw(row, x + width - 10, size.rjust(10), attr)
    if isinstance(panel, RemotePanel) and panel.error:
        msg = panel.error[: width]
        safe_draw(y + min(len(panel.entries) + 1, curses.LINES - 2), x, msg.ljust(width), curses.A_BOLD)

class FilePreviewer(Protocol):
    def can_handle(self, entry: Entry) -> bool: ...
    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        loop: asyncio.AbstractEventLoop,
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None: ...


class WavPreviewer:
    def can_handle(self, entry: Entry) -> bool:
        return entry.name.lower().endswith(".wav")

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        loop: asyncio.AbstractEventLoop,
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        try:
            loop.run_until_complete(client.play_audio(app_id, rel_path))
            status.append(f"Playing {entry.name}")
        except Exception as exc:  # noqa: BLE001
            status.append(f"Audio play failed: {exc}")


class TxtPreviewer:
    def can_handle(self, entry: Entry) -> bool:
        return entry.name.lower().endswith((".txt", ".log", ".cfg", ".ini"))

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        loop: asyncio.AbstractEventLoop,
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        try:
            data = loop.run_until_complete(client.read_storage_file(entry.path or entry.name))
            text = data.decode("utf-8", errors="ignore")
            first_line = text.splitlines()[0] if text else ""
            payload = types.DisplayElements(
                app_id=app_id,
                elements=[
                    types.TextElement(
                        id="text-preview",
                        x=0,
                        y=0,
                        text=first_line[:72] or entry.name,
                        display=types.DisplayName.FRONT,
                    )
                ],
            )
            loop.run_until_complete(client.draw_on_display(payload))
            status.append(f"Preview: {first_line[:60]}")
        except Exception as exc:  # noqa: BLE001
            status.append(f"Text preview failed: {exc}")


class PngPreviewer:
    def can_handle(self, entry: Entry) -> bool:
        return entry.name.lower().endswith((".png", ".anim"))

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        loop: asyncio.AbstractEventLoop,
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        try:
            payload = types.DisplayElements(
                app_id=app_id,
                elements=[
                    types.ImageElement(
                        id="png-preview",
                        x=0,
                        y=0,
                        path=rel_path,
                        display=types.DisplayName.FRONT,
                    )
                ],
            )
            loop.run_until_complete(client.draw_on_display(payload))
            status.append(f"Shown {entry.name} on display")
        except Exception as exc:  # noqa: BLE001
            status.append(f"PNG preview failed: {exc}")


class DefaultPreviewer:
    def can_handle(self, entry: Entry) -> bool:
        return True

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        loop: asyncio.AbstractEventLoop,
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        status.append(f"Preview not supported for {entry.name}")


PREVIEW_HANDLERS: list[FilePreviewer] = [WavPreviewer(), TxtPreviewer(), PngPreviewer(), DefaultPreviewer()]


def preview_remote(panel: Panel, status: list[str], loop: asyncio.AbstractEventLoop) -> None:
    if not isinstance(panel, RemotePanel):
        status.append("Preview available only on BusyBar panel")
        return
    entry = panel.selected
    if entry.is_dir or entry.name == "..":
        status.append("Preview only for files")
        return
    entry.path = entry.path or panel.path_of(entry)
    if not entry.path.startswith("/ext/assets/"):
        status.append("Preview works only under /ext/assets")
        return
    parts = entry.path[len("/ext/assets/") :].lstrip("/").split("/", 1)
    if not parts or not parts[0]:
        status.append("Select app folder under /ext/assets")
        return
    app_id = parts[0]
    rel_path = parts[1] if len(parts) > 1 else entry.name
    for handler in PREVIEW_HANDLERS:
        if handler.can_handle(entry):
            handler.preview(panel.client, entry, loop, status, app_id=app_id, rel_path=rel_path)
            return


def _draw_progress_modal(stdscr: curses.window, title: str, progress: float) -> None:
    """Render centered progress bar modal."""
    height, width = 5, 50
    top = max(0, (curses.LINES - height) // 2)
    left = max(0, (curses.COLS - width) // 2)
    try:
        stdscr.addnstr(top, left, "+" + "-" * (width - 2) + "+", width, curses.A_REVERSE)
        for i in range(1, height - 1):
            stdscr.addnstr(top + i, left, "|" + " " * (width - 2) + "|", width, curses.A_REVERSE)
        stdscr.addnstr(top + height - 1, left, "+" + "-" * (width - 2) + "+", width, curses.A_REVERSE)
        title_trim = title[: width - 4]
        stdscr.addnstr(top + 1, left + 2, title_trim.ljust(width - 4), width - 4, curses.A_BOLD)
        bar_width = width - 4
        filled = max(0, min(bar_width, int(bar_width * progress)))
        bar = "[" + "#" * filled + "-" * (bar_width - filled) + "]"
        stdscr.addnstr(top + 3, left + 1, bar[: bar_width + 2], bar_width + 2, curses.A_REVERSE)
        stdscr.refresh()
    except curses.error:
        pass


def copy_file(
    src_panel: Panel,
    dst_panel: Panel,
    status: list[str],
    loop: asyncio.AbstractEventLoop,
    stdscr: curses.window,
) -> None:
    entry = src_panel.selected
    if entry.is_dir or entry.name == "..":
        status.append("Skip: directories not supported for copy")
        return
    src_path = src_panel.path_of(entry)
    dst_path = dst_panel.dest_path(entry.name)
    try:
        _draw_progress_modal(stdscr, f"Copying {entry.name}", 0.1)
        if isinstance(src_panel, LocalPanel) and isinstance(dst_panel, RemotePanel):
            data = Path(src_path).read_bytes()
            _draw_progress_modal(stdscr, f"Copying {entry.name}", 0.5)
            loop.run_until_complete(dst_panel.client.write_storage_file(dst_path, data))
        elif isinstance(src_panel, RemotePanel) and isinstance(dst_panel, LocalPanel):
            data = loop.run_until_complete(src_panel.client.read_storage_file(src_path))
            _draw_progress_modal(stdscr, f"Copying {entry.name}", 0.5)
            Path(dst_path).write_bytes(data)
        else:
            status.append("Copy between same panel types not supported")
            return
        dst_panel.refresh()
        _draw_progress_modal(stdscr, f"Copying {entry.name}", 1.0)
        status.append(f"Copied {entry.name}")
    except Exception as exc:  # noqa: BLE001
        status.append(f"Copy failed: {exc}")
    finally:
        try:
            stdscr.touchwin()
            stdscr.refresh()
        except curses.error:
            pass


def confirm(stdscr: curses.window, message: str) -> bool:
    row = curses.LINES // 2
    col = max(0, (curses.COLS - len(message) - 4) // 2)
    try:
        stdscr.addnstr(row, col, f"[{message}] y/N", curses.COLS - col, curses.A_BOLD | curses.A_REVERSE)
        stdscr.refresh()
    except curses.error:
        return False
    ch = stdscr.getch()
    return ch in (ord("y"), ord("Y"))


def delete_entry(panel: Panel, stdscr: curses.window, status: list[str], loop: asyncio.AbstractEventLoop) -> None:
    entry = panel.selected
    if entry.name == "..":
        return
    if not confirm(stdscr, f"Delete {entry.name}?"):
        status.append("Delete cancelled")
        return
    try:
        if isinstance(panel, LocalPanel):
            path = Path(panel.path_of(entry))
            if entry.is_dir:
                path.rmdir()
            else:
                path.unlink()
        else:
            loop.run_until_complete(panel.client.remove_storage_file(panel.path_of(entry)))
        panel.refresh()
        status.append(f"Deleted {entry.name}")
    except Exception as exc:  # noqa: BLE001
        status.append(f"Delete failed: {exc}")


def run_ui(stdscr: curses.window, client: AsyncBusyBar) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)

    root_dir = Path(os.getcwd())
    loop = asyncio.get_event_loop()
    left = LocalPanel(root_dir)
    right = RemotePanel(client, loop)
    active_left = True
    preview_active = False
    status: list[str] = ["Ctrl+Q to quit, Tab to switch, Enter to open, F5 to copy"]

    while True:
        stdscr.clear()
        half = curses.COLS // 2
        draw_panel(stdscr, left, 0, 0, half - 1, active_left)
        draw_panel(stdscr, right, 0, half + 1, curses.COLS - half - 1, not active_left)
        # separator
        for row in range(min(curses.LINES, max(len(left.entries), len(right.entries)) + 3)):
            try:
                stdscr.addch(row, half, "│")
            except curses.error:
                pass
        if status:
            row = curses.LINES - 1
            if row >= 0:
                msg = status[-1][: curses.COLS]
                try:
                    stdscr.addnstr(row, 0, msg.ljust(curses.COLS), curses.COLS, curses.A_BOLD)
                except curses.error:
                    pass
        stdscr.refresh()

        key = stdscr.getch()
        panel = left if active_left else right
        other = right if active_left else left

        if key in (curses.ascii.ctrl("q"), 17, ord("q"), ord("Q")):  # Ctrl+Q (fallbacks)
            break
        if key == curses.KEY_UP:
            panel.move(-1)
        elif key == curses.KEY_DOWN:
            panel.move(1)
        elif key in (curses.KEY_ENTER, 10, 13):
            panel.enter()
        elif key == 9:  # Tab
            active_left = not active_left
        elif key == curses.KEY_F5:
            copy_file(panel, other, status, loop, stdscr)
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            delete_entry(panel, stdscr, status, loop)
        elif key == 32:  # space
            if preview_active:
                try:
                    loop.run_until_complete(right.client.clear_display())
                    status.append("Preview cleared")
                except Exception as exc:  # noqa: BLE001
                    status.append(f"Failed to clear preview: {exc}")
                preview_active = False
            else:
                preview_remote(panel, status, loop)
                preview_active = True

    curses.endwin()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BusyBar MC-like browser.")
    parser.add_argument("--addr", default=os.getenv("BUSY_ADDR", "http://10.0.4.20"), help="BusyBar address.")
    parser.add_argument("--token", default=os.getenv("BUSY_TOKEN"), help="Bearer token.")
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--log-file", default="bc.log", help="Log file path.")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(args.log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

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
                lan_token = os.getenv("BUSYLIB_LAN_TOKEN") or os.getenv("BUSY_LAN_TOKEN")
                if lan_token:
                    extra_headers["x-api-token"] = lan_token
            if not extra_headers:
                cloud_token = os.getenv("BUSYLIB_CLOUD_TOKEN") or os.getenv("BUSY_CLOUD_TOKEN")
                if cloud_token:
                    token = cloud_token

        client = AsyncBusyBar(addr=base_addr, token=token)
        if extra_headers:
            client.client.headers.update(extra_headers)
        return client

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = _build_client(args.addr, args.token)
    loop.run_until_complete(client.list_storage_files("/ext"))
    try:
        curses.wrapper(run_ui, client)
    finally:
        loop.run_until_complete(client.aclose())
        loop.close()
