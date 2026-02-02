from __future__ import annotations

import curses


def render_box(
    stdscr: curses.window,
    lines: list[str],
    *,
    bold_lines: set[int] | None = None,
    clear_only: bool = False,
) -> None:
    """
    Draw or clear a centered box with optional bold lines.

    Safely handles small terminals and ignores curses errors.
    """
    padding = 2
    content_width = max((len(line) for line in lines), default=0) + padding * 2
    box_width = min(curses.COLS - 4, max(20, content_width + 2))
    box_height = max(3, len(lines) + 4)
    top = max(0, (curses.LINES - box_height) // 2)
    left = max(0, (curses.COLS - box_width) // 2)
    try:
        for i in range(box_height):
            stdscr.addnstr(top + i, left, " " * box_width, box_width)
        if clear_only:
            stdscr.refresh()
            return
        stdscr.addnstr(top, left, "┌" + "─" * (box_width - 2) + "┐", box_width)
        stdscr.addnstr(
            top + box_height - 1, left, "└" + "─" * (box_width - 2) + "┘", box_width
        )
        inner_width = box_width - 2
        for idx, line in enumerate(lines):
            line_idx = top + 1 + idx
            text = line.center(inner_width)
            attr = (
                curses.A_BOLD if bold_lines and idx in bold_lines else curses.A_NORMAL
            )
            stdscr.addnstr(line_idx, left, f"│{text}│", box_width, attr)
        for pad_idx in range(len(lines), box_height - 2):
            stdscr.addnstr(
                top + 1 + pad_idx, left, "│" + " " * inner_width + "│", box_width
            )
        stdscr.refresh()
    except curses.error:
        return


def prompt_choice(
    stdscr: curses.window,
    message: str,
    choices: dict[str, object],
) -> object | None:
    """
    Display a centered prompt and map a pressed key to a choice.

    Returns the mapped value or None if key is unmapped.
    """
    render_box(stdscr, [message], bold_lines={0})
    ch = stdscr.getch()
    render_box(stdscr, [], clear_only=True)
    return choices.get(chr(ch), None)


def confirm(stdscr: curses.window, message: str) -> bool:
    """
    Ask for a yes/no confirmation prompt.

    Defaults to No and accepts both lowercase and uppercase Y.
    """
    return bool(
        prompt_choice(
            stdscr,
            f"{message} (y/N)",
            {"y": True, "Y": True},
        )
    )


def draw_progress_modal(stdscr: curses.window, title: str, progress: float) -> None:
    """
    Render a centered progress bar modal.

    The bar is capped between 0 and 100%.
    """
    bar_width = 40
    filled = max(0, min(bar_width, int(bar_width * progress)))
    bar = "[" + "#" * filled + "-" * (bar_width - filled) + "]"
    render_box(stdscr, [title, bar], bold_lines={0})


def clear_progress_modal(stdscr: curses.window) -> None:
    """
    Clear the area where the progress modal is displayed.

    Keeps the rest of the UI intact.
    """
    height, width = 5, 50
    top = max(0, (curses.LINES - height) // 2)
    left = max(0, (curses.COLS - width) // 2)
    try:
        for i in range(height):
            stdscr.addnstr(top + i, left, " " * width, width)
        stdscr.refresh()
    except curses.error:
        pass


def draw_progress_footer(stdscr: curses.window, text: str) -> None:
    """
    Draw a progress text line in the footer area.

    Uses the second-to-last line to avoid clobbering the status line.
    """
    row = curses.LINES - 2
    try:
        stdscr.addnstr(row, 0, text.ljust(curses.COLS), curses.COLS, curses.A_NORMAL)
        stdscr.refresh()
    except curses.error:
        pass


def clear_progress_footer(stdscr: curses.window) -> None:
    """
    Clear the progress footer line.

    Ignores errors if terminal geometry is too small.
    """
    row = curses.LINES - 2
    try:
        stdscr.addnstr(row, 0, " " * curses.COLS, curses.COLS)
        stdscr.refresh()
    except curses.error:
        pass
