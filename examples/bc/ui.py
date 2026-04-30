from __future__ import annotations

import curses
import curses.ascii
import logging
import os
import signal
from pathlib import Path

from busylib.client import AsyncBusyBar

from examples.bc.panels import LocalPanel, Panel, RemotePanel, draw_panel
from examples.bc.preview import (
    PreviewMode,
    preview_remote,
    preview_thread_alive,
    stop_preview_thread,
)
from examples.bc.runner import AsyncRunner
from examples.bc.state import disable_flow_control, load_state, restore_term, save_state
from examples.bc.transfer import copy_file
from examples.bc.ui_helpers import confirm


def delete_entry(
    panel: Panel,
    stdscr: curses.window,
    status: list[str],
    runner: AsyncRunner,
) -> None:
    """
    Delete the currently selected entry after confirmation.

    Handles cancellation and refreshes the panel on success.
    """
    entry = panel.selected
    if entry.name == "..":
        return
    if not confirm(stdscr, f"Delete {entry.name}?"):
        status.append("Delete cancelled")
        return
    try:
        panel.delete(entry, runner)
        panel.refresh()
        status.append(f"Deleted {entry.name}")
    except Exception as exc:  # noqa: BLE001
        status.append(f"Delete failed: {exc}")


def run_ui(
    stdscr: curses.window,
    client: AsyncBusyBar,
    runner: AsyncRunner,
    *,
    app_dir: str | None = None,
) -> None:
    """
    Run the main curses UI loop.

    Handles input, navigation, previews, and graceful shutdown.
    """
    curses.raw()
    curses.curs_set(0)
    stdscr.keypad(True)
    saved_term = disable_flow_control()
    logging.getLogger(__name__).debug("Flow control disabled; IXON cleared")

    root_dir = Path(os.getcwd())
    left = LocalPanel(root_dir)
    right = RemotePanel(runner)
    state = load_state()
    active_left = bool(state.get("active_left", True))
    local_cwd = state.get("local_cwd")
    remote_cwd = state.get("remote_cwd")
    if isinstance(local_cwd, str):
        left.set_cwd(Path(local_cwd))
    if isinstance(remote_cwd, str):
        right.set_cwd(remote_cwd)
    elif app_dir:
        right.set_cwd(app_dir)
    preview_mode = PreviewMode.NONE
    status: list[str] = ["Ctrl+Q to quit, Tab to switch, Enter to open, F5 to copy"]

    stop_flag = False

    def _stop_handler(signum, _frame) -> None:  # type: ignore[override]
        """
        Capture SIGINT/SIGTERM to stop the UI loop.

        Uses a flag to exit the main loop gracefully.
        """
        nonlocal stop_flag
        stop_flag = True

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    try:
        while not stop_flag:
            stdscr.clear()
            half = curses.COLS // 2
            draw_panel(stdscr, left, 0, 0, half - 1, active_left)
            draw_panel(
                stdscr,
                right,
                0,
                half + 1,
                curses.COLS - half - 1,
                not active_left,
            )
            for row in range(
                min(curses.LINES, max(len(left.entries), len(right.entries)) + 3)
            ):
                try:
                    stdscr.addch(row, half, "│")
                except curses.error:
                    pass
            if status:
                row = curses.LINES - 1
                if row >= 0:
                    msg = status[-1][: curses.COLS]
                    try:
                        stdscr.addnstr(
                            row,
                            0,
                            msg.ljust(curses.COLS),
                            curses.COLS,
                            curses.A_BOLD,
                        )
                    except curses.error:
                        pass
            stdscr.refresh()

            key = stdscr.getch()
            panel = left if active_left else right
            other = right if active_left else left

            logging.getLogger(__name__).debug("Key pressed: %s", key)
            if key in (
                curses.ascii.ctrl("q"),
                17,
                ord("q"),
                ord("Q"),
            ):
                break
            if key == curses.KEY_UP:
                panel.move(-1)
            elif key == curses.KEY_DOWN:
                panel.move(1)
            elif key in (curses.KEY_ENTER, 10, 13):
                panel.enter()
            elif key == 9:
                active_left = not active_left
            elif key == curses.KEY_F5:
                copy_file(panel, other, status, runner, stdscr, app_dir=app_dir)
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                delete_entry(panel, stdscr, status, runner)
            elif key == 32:
                if preview_mode is not PreviewMode.NONE:
                    try:
                        stop_preview_thread(timeout=0.1)
                        runner.run(client.stop_sound())
                        right_client = right.runner.require_client()
                        runner.run(right_client.clear_display())  # type: ignore[attr-defined]
                        status.append("Preview cleared")
                    except Exception as exc:  # noqa: BLE001
                        status.append(f"Failed to clear preview: {exc}")
                    preview_mode = PreviewMode.NONE
                else:
                    preview_mode = preview_remote(panel, status, runner)

            if preview_mode is PreviewMode.THREAD and not preview_thread_alive():
                preview_mode = PreviewMode.NONE
    except (KeyboardInterrupt, SystemExit):
        status.append("Interrupted, exiting…")
    finally:
        try:
            if preview_mode is not PreviewMode.NONE:
                stop_preview_thread(timeout=0.2)
                runner.run(client.stop_sound())
                runner.run(client.clear_display())
        except Exception:
            pass
        save_state(str(left.cwd), str(right.cwd), active_left)
        curses.endwin()
        restore_term(saved_term)
