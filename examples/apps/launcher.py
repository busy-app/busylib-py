"""
Running the programs that are not on the bar: external apps.

An external app is something a person already has on their computer - a
script that draws on the display, a bridge to some service - and wants to
start from the same place as the bar's own applications. It is a folder and
a command, run in that folder with its output kept in a log file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .model import ExternalApp, ManagerError


class Launcher:
    """
    Starts external apps and remembers which are still running.
    """

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self._running: dict[str, subprocess.Popen[bytes]] = {}

    def log_path(self, app: ExternalApp) -> Path:
        return self.log_dir / f"{app.slug}.log"

    def is_running(self, app: ExternalApp) -> bool:
        process = self._running.get(app.slug)
        if process is None:
            return False
        if process.poll() is None:
            return True
        del self._running[app.slug]
        return False

    def start(self, app: ExternalApp) -> int:
        """
        Run the app's command in its folder and return the process id.
        """
        folder = Path(app.path).expanduser()
        if not folder.is_dir():
            raise ManagerError(f"{folder} is not a folder (the path of {app.name})")
        if not app.command.strip():
            raise ManagerError(f"{app.name} has no command to run")
        if self.is_running(app):
            raise ManagerError(f"{app.name} is already running")

        self.log_dir.mkdir(parents=True, exist_ok=True)
        log = self.log_path(app).open("ab")
        log.write(f"\n--- starting: {app.command}\n".encode())
        log.flush()
        options: dict[str, object] = {}
        if sys.platform == "win32":
            # Its own process group, so closing the manager's console does
            # not take the program with it.
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        try:
            # A shell, because the command is what a person would type: it
            # may pipe, set a variable, or call something on their PATH. It
            # runs only when they ask for it, and is shown to them first.
            process = subprocess.Popen(
                app.command,
                shell=True,
                cwd=folder,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                **options,
            )
        except OSError as err:
            raise ManagerError(f"could not start {app.name}: {err}") from err
        finally:
            log.close()
        self._running[app.slug] = process
        return process.pid

    def stop(self, app: ExternalApp) -> bool:
        """
        Ask the app to end. Returns whether there was anything to stop.
        """
        process = self._running.get(app.slug)
        if process is None or process.poll() is not None:
            self._running.pop(app.slug, None)
            return False
        process.terminate()
        return True

    def stop_all(self) -> None:
        for process in self._running.values():
            if process.poll() is None:
                process.terminate()
        self._running.clear()

    def tail(self, app: ExternalApp, lines: int = 12) -> str:
        """
        The end of the app's log, for showing why it stopped.
        """
        try:
            text = self.log_path(app).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:])
