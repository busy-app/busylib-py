from __future__ import annotations

import curses
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from busylib.converter import convert_for_storage

from examples.bc.panels import LocalPanel, Panel, RemotePanel
from examples.bc.ui_helpers import (
    clear_progress_footer,
    clear_progress_modal,
    draw_progress_footer,
    draw_progress_modal,
    prompt_choice,
)

if TYPE_CHECKING:
    from examples.bc.runner import AsyncRunner


def _progress_fraction(done: int, total: int) -> float:
    """
    Compute a safe progress fraction.

    Guards against invalid totals and clamps the result to 0..1.
    """
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, done / total))


def copy_file(
    src_panel: Panel,
    dst_panel: Panel,
    status: list[str],
    runner: "AsyncRunner",
    stdscr: curses.window,
    *,
    app_dir: str | None = None,
) -> None:
    """
    Copy a file between local and remote panels.

    Handles duplicate names, conversion, progress display, and cancellation.
    """
    cancel_copy = threading.Event()

    def _handle_cancel() -> None:
        """
        Mark the copy as cancelled and update status.

        Used when the user decides to abort.
        """
        cancel_copy.set()
        status.append("Copy cancelled")

    entry = src_panel.selected
    if entry.is_dir or entry.name == "..":
        status.append("Skip: directories not supported for copy")
        return
    src_path = src_panel.path_of(entry)
    target_dir = app_dir if isinstance(dst_panel, RemotePanel) and app_dir else None
    dst_path = (
        str(Path(target_dir) / entry.name)
        if target_dir
        else dst_panel.dest_path(entry.name)
    )

    def _check_exists(path: str, directory: str | None) -> str | None:
        """
        Resolve duplicate file name handling for destinations.

        Asks user whether to cancel, replace, or keep both.
        """
        if isinstance(dst_panel, RemotePanel):
            client = dst_panel.runner.require_client()
            listing = dst_panel.runner.run(
                client.list_storage_files(directory or dst_panel.cwd)
            )  # type: ignore[attr-defined]
            names = {e.name for e in listing.list if e.type == "file"}
            name = Path(path).name
            if name not in names:
                return name
            while True:
                clear_progress_modal(stdscr)
                clear_progress_footer(stdscr)
                choice = prompt_choice(
                    stdscr,
                    f"File {name} exists: (c)ancel / (r)eplace / (k)eep both",
                    {
                        "c": "cancel",
                        "C": "cancel",
                        "r": "replace",
                        "R": "replace",
                        "k": "keep",
                        "K": "keep",
                    },
                )
                if choice == "cancel":
                    _handle_cancel()
                    return None
                if choice == "replace":
                    return name
                if choice == "keep":
                    stem = Path(name).stem
                    suffix = Path(name).suffix
                    idx = 1
                    new_name = f"{stem}_{idx}{suffix}"
                    while f"{new_name}" in names:
                        idx += 1
                        new_name = f"{stem}_{idx}{suffix}"
                    return new_name
        return None

    try:
        draw_progress_modal(stdscr, f"Copying {entry.name}", 0.1)
        if isinstance(src_panel, LocalPanel) and isinstance(dst_panel, RemotePanel):
            client = dst_panel.runner.require_client()
            target_name = _check_exists(dst_path, target_dir) or Path(dst_path).name
            if cancel_copy.is_set():
                return
            data = Path(src_path).read_bytes()
            draw_progress_modal(stdscr, f"Converting {entry.name}", 0.2)
            new_path, payload = convert_for_storage(
                str(Path(target_dir or dst_panel.cwd) / target_name),
                data,
            )
            total = len(payload)

            def _progress(done: int, _total: int) -> None:
                """
                Update the modal and footer for upload progress.

                Uses bytes transferred to compute fractions.
                """
                if cancel_copy.is_set():
                    return
                total_bytes = _total or total
                fraction = _progress_fraction(done, total_bytes)
                draw_progress_modal(
                    stdscr,
                    f"Copying {entry.name}",
                    0.2 + fraction * 0.8,
                )
                draw_progress_footer(
                    stdscr,
                    f"Uploading {done}/{total_bytes} bytes",
                )

            runner.run(
                client.write_storage_file(
                    new_path,
                    payload,
                    progress_callback=_progress,
                )
            )
            dst_panel.refresh()
        elif isinstance(src_panel, RemotePanel) and isinstance(dst_panel, LocalPanel):
            if Path(dst_path).exists():
                choice = _check_exists(dst_path, None)
                if choice is None:
                    return
                dst_path = str(Path(dst_panel.cwd) / choice)
            client = src_panel.runner.require_client()
            data = runner.run(client.read_storage_file(src_path))
            draw_progress_modal(stdscr, f"Copying {entry.name}", 0.5)
            Path(dst_path).write_bytes(data)
            dst_panel.refresh()
        else:
            status.append("Copy between same panel types not supported")
            return
        if target_dir and dst_panel.cwd != target_dir:
            dst_panel.cwd = target_dir
            dst_panel.refresh()
        draw_progress_modal(stdscr, f"Copying {entry.name}", 1.0)
        if cancel_copy.is_set():
            status.append("Copy cancelled")
        else:
            status.append(f"Copied {entry.name}")
    except Exception as exc:  # noqa: BLE001
        status.append(f"Copy failed: {exc}")
    finally:
        clear_progress_modal(stdscr)
        clear_progress_footer(stdscr)
        try:
            stdscr.touchwin()
            stdscr.refresh()
        except curses.error:
            pass
