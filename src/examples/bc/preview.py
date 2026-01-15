from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from busylib import display, types
from busylib.client import AsyncBusyBar

from .models import Entry

if TYPE_CHECKING:
    from .panels import Panel
    from .runner import AsyncRunner


class FilePreviewer(Protocol):
    """
    Protocol for file preview handlers.

    Each handler decides if it can handle an entry and performs preview.
    """

    def can_handle(self, entry: Entry) -> bool:
        """
        Return True if the previewer supports the given entry.

        Used to pick the first applicable preview handler.
        """
        ...

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        runner: "AsyncRunner",
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        """
        Execute preview action for the entry.

        Implementations may call BusyBar APIs and update status messages.
        """
        ...


class PreviewMode(str, Enum):
    """
    Preview activity mode for the UI.

    Used to decide whether the user can stop a preview or auto-clear it.
    """

    NONE = "none"
    STATIC = "static"
    THREAD = "thread"
    AUDIO = "audio"


class WavPreviewer:
    """
    Previewer for WAV audio files.

    Uses BusyBar audio playback to preview sounds.
    """

    def can_handle(self, entry: Entry) -> bool:
        """
        Check if the entry is a WAV file.

        Uses case-insensitive extension matching.
        """
        return entry.name.lower().endswith(".wav")

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        runner: "AsyncRunner",
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        """
        Trigger audio playback on the BusyBar device.

        Adds a status message on success or failure.
        """
        try:
            runner.run(client.play_audio(app_id, rel_path))
            status.append(f"Playing {entry.name} (press space to stop)")
        except Exception as exc:  # noqa: BLE001
            status.append(f"Audio play failed: {exc}")


class TxtPreviewer:
    """
    Previewer for text-like files.

    Reads the first line and shows it on the BusyBar display.
    """

    def can_handle(self, entry: Entry) -> bool:
        """
        Check if the entry is a text file.

        Supports common text extensions.
        """
        return entry.name.lower().endswith((".txt", ".log", ".cfg", ".ini"))

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        runner: "AsyncRunner",
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        """
        Read the file and display its first line.

        Shows text on the front display using the small font.
        """
        try:
            data = runner.run(client.read_storage_file(entry.path or entry.name))
            text = data.decode("utf-8", errors="ignore")
            first_line = text.splitlines()[0] if text else ""
            payload = types.DisplayElements(
                app_id=app_id,
                elements=[
                    types.TextElement(
                        id="text-preview",
                        x=0,
                        y=0,
                        text=first_line,
                        font="small",
                        display=types.DisplayName.FRONT,
                    )
                ],
            )
            runner.run(client.draw_on_display(payload))
            status.append(f"Preview: {first_line[:60]}")
        except Exception as exc:  # noqa: BLE001
            status.append(f"Text preview failed: {exc}")


class PngPreviewer:
    """
    Previewer for PNG and animation assets.

    Draws images on the BusyBar display.
    """

    def can_handle(self, entry: Entry) -> bool:
        """
        Check if the entry is an image or animation.

        Supports .png and .anim extensions.
        """
        return entry.name.lower().endswith((".png", ".anim"))

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        runner: "AsyncRunner",
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        """
        Draw the image on the BusyBar display.

        Uses the front display and updates status.
        """
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
            runner.run(client.draw_on_display(payload))
            status.append(f"Shown {entry.name} on display")
        except Exception as exc:  # noqa: BLE001
            status.append(f"PNG preview failed: {exc}")


class DefaultPreviewer:
    """
    Fallback previewer for unsupported files.

    Reports that preview is not available.
    """

    def can_handle(self, entry: Entry) -> bool:
        """
        Always return True for fallback handling.

        This previewer is intended to be last in the list.
        """
        return True

    def preview(
        self,
        client: AsyncBusyBar,
        entry: Entry,
        runner: "AsyncRunner",
        status: list[str],
        *,
        app_id: str,
        rel_path: str,
    ) -> None:
        """
        Report unsupported preview.

        Adds a status message without contacting the device.
        """
        status.append(f"Preview not supported for {entry.name}")


PREVIEW_HANDLERS: list[FilePreviewer] = [
    WavPreviewer(),
    TxtPreviewer(),
    PngPreviewer(),
    DefaultPreviewer(),
]
_preview_thread: threading.Thread | None = None
_preview_cancel = threading.Event()


def start_text_preview_thread(
    app_id: str,
    rel_path: str,
    client: AsyncBusyBar,
    runner: "AsyncRunner",
    lines: list[str],
) -> None:
    """
    Start a background thread that scrolls text lines on display.

    Cancels any existing preview thread before starting a new one.
    """
    global _preview_thread
    _preview_cancel.set()
    if _preview_thread and _preview_thread.is_alive():
        _preview_thread.join(timeout=0.2)
    _preview_cancel.clear()

    def _run() -> None:
        """
        Thread body for text preview.

        Cycles through lines and clears display on completion.
        """
        try:
            spec = display.get_display_spec(display.DisplayName.FRONT)
            width = spec.width
            height = spec.height
            runner.run(client.clear_display())
            center_y = height // 4
            for line in lines:
                if _preview_cancel.is_set():
                    break
                payload = types.DisplayElements(
                    app_id=app_id,
                    elements=[
                        types.TextElement(
                            id="text-preview",
                            x=0,
                            y=center_y,
                            text=line,
                            font="medium",
                            width=width,
                            scroll_rate=1000,
                            display=types.DisplayName.FRONT,
                        )
                    ],
                )
                runner.run(client.draw_on_display(payload))
                for _ in range(5):
                    if _preview_cancel.is_set():
                        break
                    time.sleep(0.5)
            runner.run(client.clear_display())
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).debug("Preview thread failed: %s", exc)
        finally:
            _preview_cancel.set()

    _preview_thread = threading.Thread(target=_run, daemon=True)
    _preview_thread.start()


def stop_preview_thread(timeout: float = 0.2) -> None:
    """
    Stop the current preview thread if running.

    Signals cancellation and joins with a short timeout.
    """
    global _preview_thread
    _preview_cancel.set()
    if _preview_thread and _preview_thread.is_alive():
        _preview_thread.join(timeout=timeout)
    _preview_thread = None


def preview_thread_alive() -> bool:
    """
    Return True if a preview thread is currently active.

    Used by the UI loop to detect preview completion.
    """
    return bool(_preview_thread and _preview_thread.is_alive())


def preview_mode_for_entry(entry: Entry) -> PreviewMode:
    """
    Determine preview mode based on file extension.

    Returns audio, static, or none for known file types.
    """
    lower = entry.name.lower()
    if lower.endswith(".wav"):
        return PreviewMode.AUDIO
    if lower.endswith((".png", ".anim")):
        return PreviewMode.STATIC
    return PreviewMode.NONE


def preview_remote(
    panel: "Panel",
    status: list[str],
    runner: "AsyncRunner",
) -> PreviewMode:
    """
    Preview the selected remote file if supported.

    Returns the preview mode to control UI behavior.
    """
    from .panels import RemotePanel

    if not isinstance(panel, RemotePanel):
        status.append("Preview available only on BusyBar panel")
        return PreviewMode.NONE
    client = panel.runner.require_client()
    entry = panel.selected
    if entry.is_dir or entry.name == "..":
        status.append("Preview only for files")
        return PreviewMode.NONE
    entry.path = entry.path or panel.path_of(entry)
    if not entry.path.startswith("/ext/assets/"):
        status.append("Preview works only under /ext/assets")
        return PreviewMode.NONE
    parts = entry.path[len("/ext/assets/") :].lstrip("/").split("/", 1)
    if not parts or not parts[0]:
        status.append("Select app folder under /ext/assets")
        return PreviewMode.NONE
    app_id = parts[0]
    rel_path = parts[1] if len(parts) > 1 else entry.name
    if entry.name.lower().endswith(
        (".txt", ".log", ".cfg", ".ini", ".json", ".yaml", ".yml", ".toml")
    ):
        try:
            data = runner.run(client.read_storage_file(entry.path))  # type: ignore[arg-type]
            text = data.decode("utf-8", errors="ignore").splitlines()
            start_text_preview_thread(
                app_id,
                rel_path,
                client,
                runner,
                text,
            )  # type: ignore[arg-type]
            status.append(f"Previewing {entry.name} (press space to stop)")
            return PreviewMode.THREAD
        except Exception as exc:  # noqa: BLE001
            status.append(f"Preview failed: {exc}")
            return PreviewMode.NONE
    for handler in PREVIEW_HANDLERS:
        if handler.can_handle(entry):
            handler.preview(
                client,
                entry,
                runner,
                status,
                app_id=app_id,
                rel_path=rel_path,
            )  # type: ignore[arg-type]
            return preview_mode_for_entry(entry)
    return PreviewMode.NONE
