from __future__ import annotations

import shlex
import sys
import time
from pathlib import Path

import pytest

from examples.manager.launcher import Launcher, format_env, parse_env
from examples.manager.model import ExternalApp, ManagerError

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


# What a command may say ---------------------------------------------------------


def test_the_bar_and_the_interpreter_are_filled_in_when_it_runs(tmp_path: Path) -> None:
    app = ExternalApp("c", "C", str(tmp_path), "{python} app.py --host {host}")
    launcher = Launcher(tmp_path / "logs", host="192.168.1.20")

    command = launcher.command_for(app)

    assert command.endswith("app.py --host 192.168.1.20")
    assert sys.executable in command.replace("'", "")


def test_a_program_with_its_own_interpreter_is_run_with_it(tmp_path: Path) -> None:
    app = ExternalApp(
        "c", "C", str(tmp_path), "{python} app.py", python="/opt/venv/bin/python"
    )

    assert Launcher(tmp_path / "logs").command_for(app) == "/opt/venv/bin/python app.py"


def test_a_program_follows_the_bar_the_manager_is_connected_to(tmp_path: Path) -> None:
    app = ExternalApp("c", "C", str(tmp_path), "run --host {host}")

    assert (
        Launcher(tmp_path / "logs", host="10.0.0.5:8080")
        .command_for(app)
        .endswith("10.0.0.5:8080")
    )
    assert (
        Launcher(tmp_path / "logs", host="").command_for(app).endswith("10.0.4.20")
    ), "with no bar it is the address a bar over USB always has"


def test_other_braces_in_a_command_are_left_alone(tmp_path: Path) -> None:
    command = """awk '{print $1}' x; echo '{"a": 1}' {host}"""
    app = ExternalApp("c", "C", str(tmp_path), command)

    assert Launcher(tmp_path / "logs", host="h").command_for(app) == command.replace(
        "{host}", "h"
    )


def test_a_host_with_something_odd_in_it_cannot_become_a_second_command(
    tmp_path: Path,
) -> None:
    app = ExternalApp("c", "C", str(tmp_path), "run {host}")
    launcher = Launcher(tmp_path / "logs", host="1.2.3.4; touch /tmp/pwned")

    assert launcher.command_for(app) == "run '1.2.3.4; touch /tmp/pwned'"


def test_the_environment_reaches_the_program_and_only_what_was_typed(
    tmp_path: Path,
) -> None:
    app = ExternalApp(
        "env",
        "Env",
        str(tmp_path),
        _python("import os; print(os.environ.get('CITY'), os.environ.get('UNSET'))"),
        env={"CITY": "Utrecht"},
    )
    launcher = Launcher(tmp_path / "logs")

    launcher.start(app)
    _wait(launcher, app, running=False)

    assert "Utrecht None" in launcher.tail(app)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", {}),
        ("A=1", {"A": "1"}),
        ('CITY="New York" KEY=abc', {"CITY": "New York", "KEY": "abc"}),
        ("EMPTY=", {"EMPTY": ""}),
        ("URL=http://x/?a=b", {"URL": "http://x/?a=b"}),
    ],
)
def test_environment_typed_into_a_form(text: str, expected: dict[str, str]) -> None:

    assert parse_env(text) == expected


@pytest.mark.parametrize("text", ["justaword", "1BAD=x", "A B=c", "=x", 'A="open'])
def test_environment_that_is_not_key_value_is_refused(text: str) -> None:

    with pytest.raises(ManagerError):
        parse_env(text)


def test_environment_survives_the_trip_through_a_form() -> None:

    env = {"CITY": "New York", "KEY": "a b'c", "EMPTY": ""}

    assert parse_env(format_env(env)) == env
