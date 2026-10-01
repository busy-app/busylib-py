"""
Running the programs that are not on the bar: external apps.

An external app is something a person already has on their computer - a
script that draws on the display, a bridge to some service - and wants to
start from the same place as the bar's own applications. It is a folder and
a command, run in that folder with its output kept in a log file.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from .model import ExternalApp, ManagerError


# Where a bar is when nothing says otherwise: over USB it is always here, and
# the programs in the community catalog default to it too.
USB_HOST = "10.0.4.20"

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote(word: str) -> str:
    """
    One word, quoted for the shell this system runs commands through.
    """
    if sys.platform == "win32":
        return subprocess.list2cmdline([word])
    return shlex.quote(word)


def parse_env(text: str) -> dict[str, str]:
    """
    `KEY=value OTHER="two words"` as typed into a form, as a mapping.
    """
    found: dict[str, str] = {}
    try:
        words = shlex.split(text, posix=sys.platform != "win32")
    except ValueError as err:
        raise ManagerError(f"could not read the environment ({err})") from err
    for word in words:
        key, equals, value = word.partition("=")
        if not equals or not _ENV_NAME.match(key):
            raise ManagerError(f"{word!r} is not KEY=value")
        found[key] = value
    return found


def format_env(env: dict[str, str]) -> str:
    return " ".join(f"{key}={quote(value)}" for key, value in env.items())


class Launcher:
    """
    Starts external apps and remembers which are still running.
    """

    def __init__(self, log_dir: Path, host: str = USB_HOST) -> None:
        self.log_dir = log_dir
        # The bar the manager is connected to, which `{host}` stands for.
        self.host = host or USB_HOST
        self._running: dict[str, subprocess.Popen[bytes]] = {}

    def command_for(self, app: ExternalApp) -> str:
        """
        The command as it will run, with `{host}` and `{python}` filled in.

        Plain replacement and not `str.format`: a command is full of braces
        that mean something else - awk, JSON, a shell's own expansions.
        """
        return app.command.replace("{host}", quote(self.host)).replace(
            "{python}", quote(app.python or sys.executable)
        )

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
        command = self.command_for(app)
        if self.is_running(app):
            raise ManagerError(f"{app.name} is already running")

        self.log_dir.mkdir(parents=True, exist_ok=True)
        log = self.log_path(app).open("ab")
        log.write(f"\n--- starting: {command}\n".encode())
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
                command,
                shell=True,
                cwd=folder,
                env={**os.environ, **app.env},
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
