from __future__ import annotations

import curses
from pathlib import Path
from typing import TYPE_CHECKING

from busylib.exceptions import BusyBarAPIError

from examples.bc.models import Entry, human_size

if TYPE_CHECKING:
    from .runner import AsyncRunner


class Panel:
    """
    Base panel abstraction for file listings.

    Provides selection mechanics and requires subclasses to implement IO.
    """

    def __init__(self) -> None:
        """
        Initialize the panel with empty entries.

        Keeps the selection index within the current entries list.
        """
        self.entries: list[Entry] = []
        self.index = 0

    @property
    def selected(self) -> Entry:
        """
        Return the currently selected entry.

        Assumes entries have been populated by refresh.
        """
        return self.entries[self.index]

    def move(self, delta: int) -> None:
        """
        Move selection by a delta with clamping.

        Ensures the index stays within valid bounds.
        """
        self.index = max(0, min(len(self.entries) - 1, self.index + delta))

    def set_index(self, value: int) -> None:
        """
        Set selection index with bounds checking.

        Used after refreshes or explicit index changes.
        """
        self.index = max(0, min(len(self.entries) - 1, value))

    def refresh(self) -> None:
        """
        Refresh panel entries from the underlying source.

        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def enter(self) -> None:
        """
        Enter the selected entry if supported.

        Used to navigate into directories.
        """
        raise NotImplementedError

    def path_of(self, entry: Entry) -> str:
        """
        Resolve the full path for an entry.

        Subclasses should return a path string suited to their backend.
        """
        raise NotImplementedError

    def dest_path(self, name: str) -> str:
        """
        Compute destination path for a new entry name.

        Used for copy operations and storage uploads.
        """
        raise NotImplementedError

    def build_entry(self, name: str, is_dir: bool, size: int) -> Entry:
        """
        Build a standard Entry object.

        Stores the destination path for later preview usage.
        """
        return Entry(name=name, is_dir=is_dir, size=size, path=self.dest_path(name))

    def delete(self, entry: Entry, runner: "AsyncRunner") -> None:
        """
        Delete the selected entry.

        Must be implemented by subclasses.
        """
        raise NotImplementedError


class LocalPanel(Panel):
    """
    Panel that lists local filesystem entries.

    Uses a root directory to constrain navigation.
    """

    def __init__(self, root: Path) -> None:
        """
        Initialize a local panel rooted at a directory.

        Starts with the root as current working directory.
        """
        super().__init__()
        self.root = root
        self.cwd = root
        self.refresh()

    def set_cwd(self, path: Path) -> None:
        """
        Change current directory if path is within root.

        Ignores invalid or out-of-root paths.
        """
        if not path.is_dir():
            return
        try:
            path.relative_to(self.root)
        except ValueError:
            return
        self.cwd = path
        self.refresh()

    def refresh(self) -> None:
        """
        Refresh local directory listing.

        Adds a parent directory entry unless at root.
        """
        items: list[Entry] = [Entry(name="..", is_dir=True, size=0)]
        for entry in sorted(
            self.cwd.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        ):
            items.append(
                self.build_entry(
                    entry.name,
                    entry.is_dir(),
                    entry.stat().st_size if entry.is_file() else 0,
                )
            )
        if self.cwd == self.root:
            self.entries = items[1:]
        else:
            self.entries = items
        self.set_index(0)

    def enter(self) -> None:
        """
        Enter a directory or navigate to parent.

        Updates the current directory and refreshes the view.
        """
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
        """
        Resolve the path for a local entry.

        Handles the parent directory pseudo entry.
        """
        if entry.name == "..":
            return str(self.cwd.parent if self.cwd != self.root else self.cwd)
        return str(self.cwd / entry.name)

    def dest_path(self, name: str) -> str:
        """
        Compute the destination path in the local panel.

        Uses the current directory as the base.
        """
        return str(self.cwd / name)

    def delete(self, entry: Entry, runner: "AsyncRunner") -> None:  # noqa: ARG002
        """
        Delete a local file or directory.

        Directories are removed only if empty.
        """
        path = Path(self.path_of(entry))
        if entry.is_dir:
            path.rmdir()
        else:
            path.unlink()


class RemotePanel(Panel):
    """
    Panel that lists remote BusyBar storage.

    Uses the AsyncRunner to perform network calls.
    """

    def __init__(self, runner: "AsyncRunner") -> None:
        """
        Initialize a remote panel at the default storage path.

        Performs initial refresh and stores last error if any.
        """
        super().__init__()
        self.runner = runner
        self.cwd = "/ext"
        self.error: str | None = None
        self.refresh()

    def set_cwd(self, path: str) -> None:
        """
        Change remote current directory.

        Ignores relative paths and refreshes the listing.
        """
        if not path.startswith("/"):
            return
        self.cwd = path
        self.refresh()

    def refresh(self) -> None:
        """
        Refresh remote storage listing.

        Captures errors to show them in the UI.
        """
        try:
            client = self.runner.require_client()
            listing = self.runner.run(client.list_storage_files(self.cwd))
            self._apply_listing(listing)
        except BusyBarAPIError as exc:
            if exc.code == 400 and self.cwd != "/ext":
                self.cwd = "/ext"
                try:
                    client = self.runner.require_client()
                    listing = self.runner.run(client.list_storage_files(self.cwd))
                    self._apply_listing(
                        listing,
                        error="Reset to /ext after 400 error",
                    )
                except Exception as inner_exc:  # noqa: BLE001
                    self._set_refresh_error(inner_exc)
                return
            self._set_refresh_error(exc)
        except Exception as exc:  # noqa: BLE001
            self._set_refresh_error(exc)

    def enter(self) -> None:
        """
        Enter a remote directory or navigate to parent.

        Updates cwd and refreshes listing.
        """
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
        """
        Resolve path for a remote entry.

        Handles parent directory pseudo entry.
        """
        if entry.name == "..":
            return self.cwd
        return (self.cwd.rstrip("/") + "/" + entry.name).replace("//", "/")

    def dest_path(self, name: str) -> str:
        """
        Compute destination path for a remote entry.

        Uses current remote directory as base.
        """
        return (self.cwd.rstrip("/") + "/" + name).replace("//", "/")

    def delete(self, entry: Entry, runner: "AsyncRunner") -> None:
        """
        Delete a remote storage entry.

        Delegates to the BusyBar client via AsyncRunner.
        """
        client = self.runner.require_client()
        runner.run(client.remove_storage_file(self.path_of(entry)))  # type: ignore[arg-type]

    def _apply_listing(self, listing: object, *, error: str | None = None) -> None:
        """
        Apply a storage listing to the panel entries.

        Sorts directories first and optionally keeps an error message.
        """
        items: list[Entry] = [Entry(name="..", is_dir=True, size=0)]
        for element in sorted(
            listing.list,
            key=lambda e: (e.type != "dir", e.name.lower()),
        ):
            size = getattr(element, "size", 0) if element.type == "file" else 0
            items.append(self.build_entry(element.name, element.type == "dir", size))
        if self.cwd == "/":
            self.entries = items[1:]
        else:
            self.entries = items
        self.error = error
        self.set_index(0)

    def _set_refresh_error(self, exc: Exception) -> None:
        """
        Record refresh failure and reset entries.

        Keeps a minimal list with the parent directory entry.
        """
        self.error = f"Remote refresh failed: {exc}"
        self.entries = [Entry(name="..", is_dir=True, size=0)]
        self.set_index(0)


def draw_panel(
    stdscr: curses.window,
    panel: Panel,
    y: int,
    x: int,
    width: int,
    active: bool,
) -> None:
    """
    Draw a panel with header and entries.

    Handles both local and remote panels with consistent layout.
    """

    def safe_draw(
        row: int,
        col: int,
        text: str,
        attr: int = curses.A_NORMAL,
    ) -> None:
        """
        Draw text safely within bounds.

        Avoids crashes for small terminal sizes.
        """
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
    if isinstance(panel, LocalPanel):
        title = f" Local: {panel.cwd}"
    elif isinstance(panel, RemotePanel):
        host = panel.runner.require_client().base_url
        title = f" Remote: {host} {panel.cwd}"
    else:
        title = f" {panel.__class__.__name__.replace('Panel', '')} "
    safe_draw(y, x, title[:width].ljust(width), title_attr)
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
        msg = panel.error[:width]
        safe_draw(
            y + min(len(panel.entries) + 1, curses.LINES - 2),
            x,
            msg.ljust(width),
            curses.A_BOLD,
        )
