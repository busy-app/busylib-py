from __future__ import annotations

import asyncio

import pytest

from busylib import display, types
from examples.remote.command_plugins import (
    AudioCommand,
    ClearCommand,
    ClockCommand,
    QuitCommand,
    TextCommand,
    build_call_handler,
)
from examples.remote.commands import CommandRegistry, register_command


class FakeClient:
    """
    Capture display payloads sent by command handlers.
    """

    def __init__(self) -> None:
        self.last_payload: types.DisplayElements | None = None
        self.clear_called = False
        self.dangerous_called = False
        self.ping_called = False
        self.blocked_called = False
        self.upload_calls: list[tuple[str, str, bytes]] = []
        self.play_calls: list[tuple[str, str]] = []

    async def draw_on_display(self, payload: types.DisplayElements) -> None:
        """
        Store the latest payload for assertions.
        """
        self.last_payload = payload

    async def clear_display(self) -> None:
        """
        Record that clear_display was requested.
        """
        self.clear_called = True

    async def set_display_brightness(self, **_kwargs: str) -> None:
        """
        Record that a dangerous method was called.
        """
        self.dangerous_called = True

    async def ping(self, **_kwargs: str) -> None:
        """
        Record that a safe method was called.
        """
        self.ping_called = True

    async def send_input_key(self, key: types.InputKey) -> None:
        """
        Record input key presses.
        """
        if not hasattr(self, "keys"):
            self.keys: list[types.InputKey] = []
        self.keys.append(key)

    async def upload_asset(self, app_id: str, filename: str, data: bytes) -> None:
        """
        Record asset upload calls.
        """
        self.upload_calls.append((app_id, filename, data))

    async def play_audio(self, app_id: str, path: str) -> None:
        """
        Record audio playback calls.
        """
        self.play_calls.append((app_id, path))

    async def aclose(self) -> None:
        """
        Record that a blocked method was called.
        """
        self.blocked_called = True


@pytest.mark.asyncio
async def test_text_command_sends_big_scroll_text() -> None:
    """
    Ensure the text command builds a scrolling big text element.
    """
    registry = CommandRegistry()
    client = FakeClient()
    register_command(registry, TextCommand(client))

    handled = await registry.handle("text hello world")
    assert handled is True
    assert client.last_payload is not None
    assert client.last_payload.app_id == "remote_command"
    element = client.last_payload.elements[0]
    assert isinstance(element, types.TextElement)
    assert element.text == "hello world"
    assert element.font == "big"
    assert element.scroll_rate == 1
    assert element.width == display.get_display_spec(display.FRONT_DISPLAY).width


@pytest.mark.asyncio
async def test_text_command_parses_key_value_args() -> None:
    """
    Ensure key=value args are parsed into options.
    """
    registry = CommandRegistry()
    client = FakeClient()
    register_command(registry, TextCommand(client))

    handled = await registry.handle(
        't "abracadabra" x=1 y=2 align=top_right scroll-rate=1000'
    )
    assert handled is True
    assert client.last_payload is not None
    element = client.last_payload.elements[0]
    assert isinstance(element, types.TextElement)
    assert element.text == "abracadabra"
    assert element.x == 1
    assert element.y == 2
    assert element.align == "top_right"
    assert element.scroll_rate == 1000


@pytest.mark.asyncio
async def test_quit_command_sets_stop_event() -> None:
    """
    Ensure quit command signals the stop event.
    """
    registry = CommandRegistry()
    stop_event = asyncio.Event()
    register_command(registry, QuitCommand(stop_event))

    handled = await registry.handle("quit")
    assert handled is True
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_quit_command_alias_sets_stop_event() -> None:
    """
    Ensure quit command aliases are registered.
    """
    registry = CommandRegistry()
    stop_event = asyncio.Event()
    register_command(registry, QuitCommand(stop_event))

    handled = await registry.handle("q")
    assert handled is True
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_clear_command_clears_terminal() -> None:
    """
    Ensure the clear command calls the display clear endpoint.
    """
    registry = CommandRegistry()
    client = FakeClient()
    register_command(registry, ClearCommand(client))

    handled = await registry.handle("clear")
    assert handled is True
    assert client.clear_called is True


@pytest.mark.asyncio
async def test_clear_command_alias_clears_terminal() -> None:
    """
    Ensure clear command aliases are registered.
    """
    registry = CommandRegistry()
    client = FakeClient()
    register_command(registry, ClearCommand(client))

    handled = await registry.handle("c")
    assert handled is True
    assert client.clear_called is True


@pytest.mark.asyncio
async def test_clock_command_sends_keys() -> None:
    """
    Ensure clock command sends the expected key sequence.
    """
    registry = CommandRegistry()
    client = FakeClient()
    register_command(registry, ClockCommand(client))

    handled = await registry.handle("clock")
    assert handled is True
    assert getattr(client, "keys", []) == [
        types.InputKey.APPS,
        types.InputKey.OK,
        types.InputKey.OK,
    ]


@pytest.mark.asyncio
async def test_audio_command_uploads_and_plays(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """
    Ensure audio command uploads the converted file and plays it.
    """
    source = tmp_path / "sound.wav"
    source.write_bytes(b"data")

    def fake_convert(path: str, data: bytes) -> tuple[str, bytes]:
        return "sound.wav", b"converted"

    monkeypatch.setattr(
        "examples.remote.command_plugins.converter.convert_for_storage",
        fake_convert,
    )

    registry = CommandRegistry()
    client = FakeClient()
    messages: list[str] = []

    def status_message(text: str) -> None:
        messages.append(text)

    register_command(registry, AudioCommand(client, status_message))

    handled = await registry.handle(f"audio {source}")
    assert handled is True
    assert client.upload_calls == [("remote", "sound.wav", b"converted")]
    assert client.play_calls == [("remote", "sound.wav")]
    assert messages == [
        "audio: reading sound.wav",
        "audio: converting",
        "audio: uploading sound.wav",
        "audio: playing sound.wav",
        "audio: done",
    ]


@pytest.mark.asyncio
async def test_call_handler_invokes_method_with_kwargs() -> None:
    """
    Ensure call handler dispatches to client methods with key=value args.
    """
    client = FakeClient()
    messages: list[str] = []

    def status_message(text: str) -> None:
        messages.append(text)

    handler = build_call_handler(client, status_message)

    await handler(["ping", "name=foo", "count=2"])
    assert client.ping_called is True
    assert any("call ping" in message for message in messages)


@pytest.mark.asyncio
async def test_call_handler_requires_force_for_dangerous_methods() -> None:
    """
    Ensure dangerous methods require --force.
    """
    client = FakeClient()
    messages: list[str] = []

    def status_message(text: str) -> None:
        messages.append(text)

    handler = build_call_handler(client, status_message)

    await handler(["set_display_brightness", "front=10"])
    assert client.dangerous_called is False
    assert any("requires --force" in message for message in messages)

    await handler(["set_display_brightness", "front=10", "--force"])
    assert client.dangerous_called is True


@pytest.mark.asyncio
async def test_call_handler_blocks_blacklisted_methods() -> None:
    """
    Ensure blacklisted methods are not invoked.
    """
    client = FakeClient()
    messages: list[str] = []

    def status_message(text: str) -> None:
        messages.append(text)

    handler = build_call_handler(client, status_message)

    await handler(["aclose", "--force"])
    assert client.blocked_called is False
    assert any("not allowed" in message for message in messages)
