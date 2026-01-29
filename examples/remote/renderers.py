from __future__ import annotations

import logging
import re
import shutil
import time

from busylib import display
from busylib.features import DeviceSnapshot
from busylib.keymap import KeyMap

from examples.remote.constants import ICON_SETS

logger = logging.getLogger(__name__)


def _human_bytes(value: int | None) -> str:
    """
    Format byte counts into a compact human-readable string.

    The output uses binary units and keeps one decimal place for large values.
    """
    units = ["B", "K", "M", "G", "T"]
    size = float(value or 0)
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.1f}{units[unit]}" if unit else f"{int(size)}B"


class TerminalRenderer:
    """
    Terminal rendering with periodic size checks and warnings.
    """

    def __init__(
        self,
        spec: display.DisplaySpec,
        spacer: str,
        pixel_char: str,
        icons: dict[str, str],
        *,
        clear_screen,
    ) -> None:
        """
        Initialize the renderer with display settings and UI assets.

        This captures icon mappings and a screen-clear callback for overlays.
        """
        self.spec = spec
        self.spacer = spacer
        self.pixel_char = pixel_char
        self.icons = icons
        self._clear_screen = clear_screen
        self._next_size_check = 0.0
        self._fits = True
        self._size_info: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._cleared = False
        front_req = self._required_size(display.FRONT_DISPLAY)
        back_req = self._required_size(display.BACK_DISPLAY)
        self._alt_required = {"front": front_req, "back": back_req}
        self._terminal_size = (80, 24)
        self._update_size(force=True)
        self._help_active = False
        self._help_keymap: KeyMap | None = None
        self._info: DeviceSnapshot | None = None
        self._usb_connected = False
        self._streaming_info: str | None = None

    def _get_terminal_size(self) -> tuple[int, int]:
        """
        Safely fetch the terminal size and fall back on the cached value.

        Some terminals can raise errors during resize events.
        """
        try:
            cols, rows = shutil.get_terminal_size(fallback=self._terminal_size)
        except (OSError, ValueError):
            return self._terminal_size
        self._terminal_size = (cols, rows)
        return cols, rows

    def _emoji_extra_width(self, *parts: str) -> int:
        """
        Estimate extra width for emoji icons in the info bar.

        Emoji icons often occupy two terminal columns.
        """
        if self.icons != ICON_SETS["emoji"]:
            return 0
        icon_values = [value for key, value in self.icons.items() if key != "pixel"]
        return sum(part.count(icon) for part in parts for icon in icon_values)

    def _update_size(self, *, force: bool = False) -> None:
        """
        Refresh cached terminal size information when needed.

        The size is recomputed at most once per second unless forced.
        """
        now = time.monotonic()
        if force or now >= self._next_size_check:
            cols, rows = self._get_terminal_size()
            req_cols, req_rows = self._required_size(self.spec)
            self._size_info = (cols, rows, req_cols, req_rows)
            self._fits = cols >= req_cols and rows >= req_rows
            self._next_size_check = now + 1.0

    def _required_size(self, spec: display.DisplaySpec) -> tuple[int, int]:
        """
        Compute the terminal size required to render a display.

        The width accounts for the pixel glyph and optional spacer.
        """
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
            self._clear_screen("render_start")
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

        header = self._format_info_line()
        body = "\n".join(lines)
        frame = header + "\n" + body if header else body
        print("\x1b[H" + frame, end="", flush=True)

    def _render_size_warning(
        self, cols: int, rows: int, required_cols: int, required_rows: int
    ) -> str:
        """
        Build a boxed warning message when the terminal is too small.

        Includes quick tips and display size requirements.
        """
        line1 = (
            f" Terminal {cols}x{rows} too small; need {required_cols}x{required_rows} "
        )
        extra: list[str] = []
        if self.spacer:
            extra.append(' Try --spacer "" for compact output ')
        front_req = self._alt_required.get("front")
        back_req = self._alt_required.get("back")
        if front_req and back_req:
            extra.append(
                f" Front needs {front_req[0]}x{front_req[1]}; Back needs {back_req[0]}x{back_req[1]} "
            )
        extra.append(" Quit: Ctrl+Q | Help: h | Switch: Tab or Ctrl+R ")
        return self._boxed([line1] + extra, top_pad_rows=rows, padding=2)

    def update_info(
        self,
        snapshot: DeviceSnapshot | None = None,
        usb_connected: bool | None = None,
        streaming_info: str | None = None,
    ) -> None:
        """
        Update the cached snapshot and USB status for the info bar.

        Passing None leaves the corresponding value unchanged.
        """
        if snapshot is not None:
            self._info = snapshot
        if usb_connected is not None:
            self._usb_connected = usb_connected
        if streaming_info is not None:
            self._streaming_info = streaming_info

    def _build_columns(self, segments: list[str], width: int) -> list[list[str]]:
        """
        Split segments into columns that fit the available width.

        Falls back to a single column if nothing fits.
        """
        if not segments:
            return []

        for col_count in (3, 2, 1):
            if col_count > len(segments):
                continue
            col_width = max(1, width // col_count)
            columns = [segments[idx::col_count] for idx in range(col_count)]
            if self._columns_fit(columns, col_width):
                return columns
        return [segments]

    def _columns_fit(self, columns: list[list[str]], width: int) -> bool:
        """
        Check whether all column entries fit within the given width.

        This uses visible lengths without ANSI escape sequences.
        """
        for column in columns:
            if any(self._visible_len(item) > width for item in column):
                return False
        return True

    def _format_info_line(self) -> str:
        """
        Compose the info bar text from the current snapshot state.

        Returns an empty string when no snapshot data is available.
        """
        snap = self._info
        if not snap:
            return ""

        cols, _rows = self._get_terminal_size()

        left_segments: list[str] = []
        if snap.name:
            streaming = (
                f"{snap.name} ({self._streaming_info})"
                if self._streaming_info
                else snap.name
            )
            left_segments.append(f"{self.icons['device']} {streaming}")
        elif self._streaming_info:
            left_segments.append(f"{self.icons['device']} {self._streaming_info}")
        if snap.system and snap.system.version:
            left_segments.append(f"{self.icons['system']} {snap.system.version}")
        if snap.storage:
            used = snap.storage.used
            total = snap.storage.total
            if total is not None:
                left_segments.append(
                    f"{self.icons['storage']} {_human_bytes(used)}/{_human_bytes(total)}"
                )

        center_segments: list[str] = []
        if snap.time:
            tzinfo = snap.time.tzinfo.tzname(snap.time) if snap.time.tzinfo else "UTC"
            center_segments.append(
                f"{self.icons['time']} {snap.time.strftime('%H:%M:%S')} {tzinfo}"
            )
        if snap.brightness:
            front = snap.brightness.front or "-"
            back = snap.brightness.back or "-"
            center_segments.append(f"{self.icons['brightness']} {front} | {back}")
        if snap.volume and snap.volume.volume is not None:
            center_segments.append(f"{self.icons['volume']} {int(snap.volume.volume)}%")

        right_segments: list[str] = []
        if snap.wifi:
            ssid = snap.wifi.ssid or ""
            right_segments.append(f"{self.icons['wifi']} {ssid}")
        if snap.power and snap.power.battery_charge is not None:
            charge = snap.power.battery_charge
            bar = (
                self.icons["battery_full"] if charge > 20 else self.icons["battery_low"]
            )
            right_segments.append(f"{bar} {charge}%")

        usb_icon = (
            self.icons["usb_connected"]
            if self._usb_connected
            else self.icons["usb_disconnected"]
        )
        right_segments.append(f"USB:{usb_icon}")

        if not (left_segments or center_segments or right_segments):
            return ""

        return self._render_infobar(
            left_segments, center_segments, right_segments, cols
        )

    def _render_infobar(
        self, left: list[str], center: list[str], right: list[str], width: int
    ) -> str:
        """
        Render left/center/right segments into a single aligned line.

        Trims segments to fit the available width.
        """
        left_part = " ".join(left)
        center_part = " ".join(center)
        right_part = " ".join(right)

        def length_with_gaps(lp: str, cp: str, rp: str) -> int:
            gaps = (
                (1 if lp and cp else 0)
                + (1 if cp and rp else 0)
                + (1 if lp and not cp and rp else 0)
            )
            extra = self._emoji_extra_width(lp, cp, rp)
            return len(lp) + len(cp) + len(rp) + gaps + extra

        # Trim until fits: center -> left (end) -> right (start)
        while length_with_gaps(left_part, center_part, right_part) > width:
            if center_part:
                center_part = center_part[:-1]
                continue
            if left_part:
                left_part = left_part[:-1]
                continue
            if right_part:
                right_part = right_part[1:]
                continue
            break

        # After trimming, spread remaining space evenly to left/right around center
        occupied = (
            len(left_part) + len(center_part) + len(right_part)
            # + sum(1 for x in left + center + right)
        )
        gaps_available = max(0, width - occupied)
        gap_left = gaps_available // 2
        gap_right = gaps_available - gap_left

        line = f"{left_part}{' ' * gap_left}{center_part}{' ' * gap_right}{right_part}"
        return line

    def render_help(self, keymap: KeyMap | None) -> None:
        """
        Toggle a brief help overlay. When active, frames are paused.
        """
        if self._help_active:
            self._hide_help()
            return
        self._show_help(keymap)

    def _render_help_frame(self) -> None:
        """
        Render the help overlay as a boxed grid of key bindings.

        The layout adapts to the current terminal width.
        """
        cols, _rows = self._get_terminal_size()
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
        visible = [self._visible_len(line) for line in lines]
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

        self._clear_screen("help_overlay", home=True)
        print(self._boxed(formatted_rows, padding=2), end="", flush=True)
        self._cleared = False

    def _show_help(self, keymap: KeyMap | None) -> None:
        """
        Activate the help overlay and render it immediately.

        This also stores the current keymap for label rendering.
        """
        self._help_active = True
        self._help_keymap = keymap
        self._render_help_frame()

    def _hide_help(self) -> None:
        """
        Hide the help overlay and mark the screen as dirty.

        The next render will redraw the frame.
        """
        self._help_active = False
        self._help_keymap = None
        self._clear_screen("help_hide")
        self._cleared = False

    def _boxed(
        self, lines: list[str], top_pad_rows: int | None = None, padding: int = 0
    ) -> str:
        """
        Wrap lines in a simple ASCII box with optional padding.

        The box is centered within the terminal dimensions.
        """
        cols, rows = self._get_terminal_size()
        stripped = [self._strip_ansi(line) for line in lines]
        max_width = max(
            10,
            min(
                cols - 4 - padding * 2,
                max(len(line) for line in stripped) if stripped else 10,
            ),
        )
        inner_width = max_width
        horizontal = "+" + "-" * (inner_width + padding * 2) + "+"
        padded_lines = []
        for raw, plain in zip(lines, stripped):
            text = plain
            if len(text) > max_width:
                text = text[: max(0, max_width - 3)] + "..."
            pad_len = inner_width - len(text)
            padded_lines.append(
                "|" + " " * padding + raw + " " * pad_len + " " * padding + "|"
            )
        block_lines = [horizontal, *padded_lines, horizontal]
        block_height = len(block_lines)
        top_pad = top_pad_rows if top_pad_rows is not None else rows
        top_pad = max(0, (top_pad - block_height) // 2)
        left_pad = max(0, (cols - len(horizontal)) // 2)
        block = "\n".join(" " * left_pad + line for line in block_lines)
        return ("\n" * top_pad) + block

    @staticmethod
    def _visible_len(text: str) -> int:
        """
        Return the visible length of a string without ANSI escapes.

        This helps align colored text in the terminal.
        """
        return len(TerminalRenderer._strip_ansi(text))

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """
        Remove ANSI color/formatting escape codes from text.

        This keeps layout calculations based on visible characters.
        """
        return re.sub(r"\x1b\[[0-9;]*m", "", text)
