import asyncio
from collections.abc import Awaitable, Callable

import pytest

from busylib.exceptions import BusyBarAPIError
from examples.remote import runner as remote_runner
from examples.remote.keymap import default_keymap


class DummyReader:
    """
    Reader stub that feeds a single key sequence.
    """

    def __init__(self, _loop, queue: asyncio.Queue[bytes]) -> None:
        """
        Store the queue for feeding input.
        """
        self.queue = queue

    def start(self) -> None:
        """
        Feed a Tab key sequence into the queue.
        """
        self.queue.put_nowait(b"\t")

    def stop(self) -> None:
        """
        No-op stop hook.
        """
        return None


class DummyClient:
    """
    Minimal client stub for input forwarding tests.
    """

    async def send_input_key(self, _key) -> None:
        """
        Ignore input key sends.
        """
        return None


@pytest.mark.asyncio
async def test_forward_keys_switches_display(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure Tab triggers a display switch callback.
    """
    switches: list[bool] = []

    def on_switch() -> None:
        """
        Record the switch invocation.
        """
        switches.append(True)

    monkeypatch.setattr(remote_runner, "StdinReader", DummyReader)

    stop_event = asyncio.Event()
    await remote_runner._forward_keys(
        client=DummyClient(),
        keymap=default_keymap(),
        stop_event=stop_event,
        renderer=None,
        on_switch=on_switch,
    )

    assert switches == [True]
    assert stop_event.is_set()


class CommandReader:
    """
    Reader stub that feeds a command and exit sequence.
    """

    def __init__(self, _loop, queue: asyncio.Queue[bytes]) -> None:
        """
        Store the queue for feeding input.
        """
        self.queue = queue

    def start(self) -> None:
        """
        Feed the command and exit sequence into the queue.
        """
        self.queue.put_nowait(b":boom\r")
        self.queue.put_nowait(b"\x11")

    def stop(self) -> None:
        """
        No-op stop hook.
        """
        return None


@pytest.mark.asyncio
async def test_forward_keys_ignores_busy_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure command errors with code 423 are reported without raising.
    """
    messages: list[str] = []

    def status_message(text: str) -> None:
        messages.append(text)

    async def handler(_args: list[str]) -> None:
        raise BusyBarAPIError("Loader is busy with another app", code=423)

    registry = remote_runner.CommandRegistry()
    registry.register("boom", handler)
    queue: asyncio.Queue[Callable[[], Awaitable[None]]] = asyncio.Queue()

    monkeypatch.setattr(remote_runner, "StdinReader", CommandReader)

    stop_event = asyncio.Event()
    worker = asyncio.create_task(
        remote_runner._run_command_queue(
            queue,
            stop_event=stop_event,
        )
    )
    await remote_runner._forward_keys(
        client=DummyClient(),
        keymap=default_keymap(),
        stop_event=stop_event,
        status_message=status_message,
        command_queue=queue,
        renderer=None,
        on_switch=None,
        command_registry=registry,
    )
    await worker

    assert stop_event.is_set()
    assert any("Loader is busy with another app" in message for message in messages)
