from __future__ import annotations

import argparse
import asyncio
import importlib

import pytest


remote_main = importlib.import_module("examples.remote.main")
remote_runner = importlib.import_module("examples.remote.runner")
remote_terminal = importlib.import_module("examples.remote.terminal_utils")


class DummyUsb:
    """
    Minimal USB stub for the periodic loop.

    The refresh method always reports disconnected.
    """

    def refresh_connection(self) -> bool:
        """
        Return a disconnected status for the dummy USB.

        This avoids network access during tests.
        """
        return False


class DummyClient:
    """
    Minimal AsyncBusyBar stub used by the remote runner.

    Only the methods accessed by the runner are implemented.
    """

    def __init__(self) -> None:
        """
        Initialize the dummy client and USB stub.

        The client does not perform real network calls.
        """
        self.usb = DummyUsb()

    async def aclose(self) -> None:
        """
        Async no-op close used by the runner cleanup.

        This keeps the event loop clean without network calls.
        """
        return None


def test_main_prints_run_error(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure main prints runner errors to stderr.

    This guards against silent failures in the CLI entry point.
    """

    async def failing_run(_args: argparse.Namespace) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(remote_main, "parse_args", lambda: argparse.Namespace())
    monkeypatch.setattr(remote_main, "_run", failing_run)

    with pytest.raises(SystemExit):
        remote_main.main()

    captured = capsys.readouterr()
    assert "Error: boom" in captured.err


def test_run_keeps_error_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure terminal is not cleared after a streaming error.

    This keeps the printed error visible for the user.
    """

    async def failing_stream_ws(**_kwargs) -> None:
        raise RuntimeError("boom")

    async def dummy_snapshot(*_args, **_kwargs) -> None:
        return None

    clear_calls: list[str] = []

    def fake_clear_terminal() -> None:
        clear_calls.append("terminal")

    def fake_clear_screen(reason: str, *, home: bool = False) -> None:
        clear_calls.append(reason)

    monkeypatch.setattr(remote_runner, "_build_client", lambda *_: DummyClient())
    monkeypatch.setattr(remote_runner, "_stream_ws", failing_stream_ws)
    monkeypatch.setattr(
        remote_runner,
        "build_periodic_tasks",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setitem(remote_runner.PERIODIC_TASKS, "info_update", 1_000_000.0)
    monkeypatch.setitem(remote_runner.PERIODIC_TASKS, "usb_check", 1_000_000.0)
    monkeypatch.setattr(remote_main, "_clear_terminal", fake_clear_terminal)
    monkeypatch.setattr(remote_main, "_clear_screen", fake_clear_screen)

    args = argparse.Namespace(
        addr="http://10.0.4.20",
        token=None,
        http_poll_interval=0.0,
        spacer=" ",
        pixel_char=remote_main.PIXEL_CHAR,
        log_level="INFO",
        log_file=None,
        no_send_input=True,
        keymap_file=None,
    )

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(remote_main._run(args))

    assert clear_calls == []


def test_print_user_message_resets_ansi(capsys) -> None:
    """
    Ensure user-facing output includes ANSI reset and the message.

    This helps keep the message readable after terminal rendering.
    """
    remote_terminal._print_user_message("Error", "boom")
    captured = capsys.readouterr()
    assert "\x1b[0m" in captured.err
    assert "Error: boom" in captured.err


def test_print_user_message_includes_addr(capsys) -> None:
    """
    Ensure address is included in user-facing error output.

    This helps identify which device endpoint failed.
    """
    remote_terminal._print_user_message("Error", "boom", addr="http://10.0.4.20")
    captured = capsys.readouterr()
    assert "addr: http://10.0.4.20" in captured.err


def test_format_error_keyboard_interrupt() -> None:
    """
    Ensure keyboard interrupt is rendered as a friendly message.

    This keeps stop messages concise and predictable.
    """
    prefix, message = remote_terminal._format_error_message(KeyboardInterrupt())
    assert prefix is None
    assert message == "Stopped"


def test_clear_screen_reports_reason(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure clear screen debug logs include the reason.

    The stdout payload should still contain the escape sequence.
    """
    monkeypatch.setattr(remote_terminal, "DEBUG_SCREEN_CLEAR", True)
    remote_terminal._clear_screen("unit-test", home=True)
    captured = capsys.readouterr()
    assert "[remote] clear_screen: unit-test" in captured.err
    assert "\x1b[2J\x1b[H" in captured.out


def test_default_args_use_ws(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure default arguments select the websocket streaming path.

    This guards the default mode against accidental HTTP polling.
    """

    async def dummy_snapshot(*_args, **_kwargs) -> None:
        return None

    async def fake_stream_ws(**kwargs) -> None:
        stop_event = kwargs["stop_event"]
        stop_event.set()

    async def forbidden_poll_http(**_kwargs) -> None:
        raise AssertionError("HTTP polling should not be used by default.")

    monkeypatch.setattr(remote_runner, "_build_client", lambda *_: DummyClient())
    monkeypatch.setattr(remote_runner, "_stream_ws", fake_stream_ws)
    monkeypatch.setattr(remote_runner, "_poll_http", forbidden_poll_http)
    monkeypatch.setattr(
        remote_runner,
        "build_periodic_tasks",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setitem(remote_runner.PERIODIC_TASKS, "info_update", 1_000_000.0)
    monkeypatch.setitem(remote_runner.PERIODIC_TASKS, "usb_check", 1_000_000.0)
    monkeypatch.setattr(remote_main, "_clear_terminal", lambda: None)

    args = argparse.Namespace(
        addr="http://10.0.4.20",
        token=None,
        http_poll_interval=None,
        spacer=" ",
        pixel_char=remote_main.PIXEL_CHAR,
        log_level="INFO",
        log_file=None,
        no_send_input=True,
        keymap_file=None,
    )

    asyncio.run(remote_main._run(args))


def test_cloud_args_force_http_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure cloud mode forces HTTP polling at 1 frame per second.
    """

    class DummyCloudClient:
        """
        Minimal cloud client stub for polling selection.
        """

        def __init__(self) -> None:
            """
            Mark the client as cloud-based.
            """
            self.is_cloud = True
            self.base_url = "https://proxy.dev.busy.app"

        async def aclose(self) -> None:
            """
            No-op async close to satisfy the runner.
            """
            return None

    async def dummy_snapshot(*_args, **_kwargs) -> None:
        return None

    async def forbidden_stream_ws(**_kwargs) -> None:
        raise AssertionError("WebSocket streaming should be disabled in cloud mode.")

    captured: dict[str, float] = {}

    async def fake_poll_http(**kwargs) -> None:
        captured["interval"] = kwargs["interval"]
        kwargs["stop_event"].set()

    monkeypatch.setattr(remote_runner, "_build_client", lambda *_: DummyCloudClient())
    monkeypatch.setattr(remote_runner, "_stream_ws", forbidden_stream_ws)
    monkeypatch.setattr(remote_runner, "_poll_http", fake_poll_http)
    monkeypatch.setattr(
        remote_runner,
        "build_periodic_tasks",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setitem(remote_runner.PERIODIC_TASKS, "info_update", 1_000_000.0)
    monkeypatch.setitem(remote_runner.PERIODIC_TASKS, "usb_check", 1_000_000.0)
    monkeypatch.setattr(remote_main, "_clear_terminal", lambda: None)

    args = argparse.Namespace(
        addr="https://proxy.dev.busy.app",
        token="token",
        http_poll_interval=None,
        spacer=" ",
        pixel_char=remote_main.PIXEL_CHAR,
        log_level="INFO",
        log_file=None,
        no_send_input=True,
        keymap_file=None,
    )

    asyncio.run(remote_main._run(args))

    assert captured["interval"] == 1.0
