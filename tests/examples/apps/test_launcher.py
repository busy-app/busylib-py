from __future__ import annotations

import shlex
import sys
import time
from pathlib import Path

import pytest

from examples.apps.launcher import Launcher
from examples.apps.model import ExternalApp, ManagerError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell commands")


def _python(code: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def _wait(launcher: Launcher, app: ExternalApp, *, running: bool) -> None:
    for _ in range(100):
        if launcher.is_running(app) is running:
            return
        time.sleep(0.05)
    raise AssertionError(f"never became running={running}")


def test_an_app_runs_in_its_folder_and_leaves_a_log(tmp_path: Path) -> None:
    folder = tmp_path / "work"
    folder.mkdir()
    app = ExternalApp(
        "hello", "Hello", str(folder), _python("import os; print(os.getcwd())")
    )
    launcher = Launcher(tmp_path / "logs")

    launcher.start(app)
    _wait(launcher, app, running=False)

    assert str(folder.resolve()) in launcher.tail(app) or folder.name in launcher.tail(
        app
    )


def test_a_folder_that_is_not_there_is_said_before_anything_runs(
    tmp_path: Path,
) -> None:
    app = ExternalApp("x", "X", str(tmp_path / "missing"), "true")

    with pytest.raises(ManagerError, match="is not a folder"):
        Launcher(tmp_path / "logs").start(app)


def test_an_app_without_a_command_is_refused(tmp_path: Path) -> None:
    app = ExternalApp("x", "X", str(tmp_path), "   ")

    with pytest.raises(ManagerError, match="no command to run"):
        Launcher(tmp_path / "logs").start(app)


def test_an_app_cannot_be_started_twice(tmp_path: Path) -> None:
    app = ExternalApp(
        "slow", "Slow", str(tmp_path), _python("import time; time.sleep(30)")
    )
    launcher = Launcher(tmp_path / "logs")
    launcher.start(app)
    try:
        with pytest.raises(ManagerError, match="already running"):
            launcher.start(app)
    finally:
        launcher.stop_all()


def test_a_running_app_can_be_stopped(tmp_path: Path) -> None:
    app = ExternalApp(
        "slow", "Slow", str(tmp_path), _python("import time; time.sleep(30)")
    )
    launcher = Launcher(tmp_path / "logs")
    launcher.start(app)
    _wait(launcher, app, running=True)

    assert launcher.stop(app) is True
    _wait(launcher, app, running=False)
    assert launcher.stop(app) is False


def test_a_failing_app_leaves_its_complaint_in_the_log(tmp_path: Path) -> None:
    app = ExternalApp(
        "bad", "Bad", str(tmp_path), _python("raise SystemExit('it broke')")
    )
    launcher = Launcher(tmp_path / "logs")

    launcher.start(app)
    _wait(launcher, app, running=False)

    assert "it broke" in launcher.tail(app)


def test_the_log_keeps_earlier_runs(tmp_path: Path) -> None:
    app = ExternalApp("twice", "Twice", str(tmp_path), _python("print('run')"))
    launcher = Launcher(tmp_path / "logs")

    for _ in range(2):
        launcher.start(app)
        _wait(launcher, app, running=False)

    assert launcher.log_path(app).read_text().count("--- starting") == 2
