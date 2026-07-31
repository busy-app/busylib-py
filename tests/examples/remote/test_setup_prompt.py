from __future__ import annotations

import asyncio

import pytest

from examples.remote.commands.record_audio import InputCapture
from examples.remote.commands.setup import CapturePrompt
from examples.setup.prompts import SetupCancelled


class Harness:
    """
    Drives a CapturePrompt by feeding raw bytes into its input capture.
    """

    def __init__(self) -> None:
        self.capture = InputCapture()
        self.messages: list[str] = []
        self.status_lines: list[str | None] = []
        self.prompt = CapturePrompt(
            self.capture,
            self.messages.append,
            self.status_lines.append,
        )

    async def feed(self, coro, *chunks: bytes):
        """
        Await `coro` while feeding it raw input chunks.
        """
        task = asyncio.ensure_future(coro)
        for chunk in chunks:
            for _ in range(100):
                if self.capture.handle(chunk):
                    break
                await asyncio.sleep(0)
            else:
                raise AssertionError("capture never became active")
        return await task


@pytest.mark.asyncio
async def test_text_reads_a_line() -> None:
    """
    Printable bytes accumulate and Enter submits the line.
    """
    h = Harness()
    value = await h.feed(h.prompt.text("SSID"), b"home", b"\r")
    assert value == "home"


@pytest.mark.asyncio
async def test_backspace_removes_last_character() -> None:
    """
    Both backspace codes delete the previous character.
    """
    h = Harness()
    value = await h.feed(h.prompt.text("SSID"), b"homez", b"\x7f", b"\r")
    assert value == "home"


@pytest.mark.asyncio
async def test_escape_cancels() -> None:
    """
    Escape aborts the prompt with SetupCancelled.
    """
    h = Harness()
    with pytest.raises(SetupCancelled):
        await h.feed(h.prompt.text("SSID"), b"ho", b"\x1b")


@pytest.mark.asyncio
async def test_empty_input_falls_back_to_default() -> None:
    """
    Submitting nothing keeps the offered default.
    """
    h = Harness()
    value = await h.feed(h.prompt.text("Timezone", default="Europe/Moscow"), b"\r")
    assert value == "Europe/Moscow"


@pytest.mark.asyncio
async def test_secret_is_masked_in_the_status_line() -> None:
    """
    A secret is echoed as asterisks and never in cleartext.
    """
    h = Harness()
    value = await h.feed(h.prompt.secret("Password"), b"hunter2", b"\r")
    assert value == "hunter2"
    painted = [line for line in h.status_lines if line]
    assert any("*******" in line for line in painted)
    assert not any("hunter2" in line for line in painted)


@pytest.mark.asyncio
async def test_status_line_is_cleared_afterwards() -> None:
    """
    The transient status line is reset once the prompt finishes.
    """
    h = Harness()
    await h.feed(h.prompt.text("SSID"), b"x", b"\r")
    assert h.status_lines[-1] is None


@pytest.mark.asyncio
async def test_confirm_defaults_on_empty_answer() -> None:
    """
    Enter alone accepts the default answer.
    """
    h = Harness()
    assert await h.feed(h.prompt.confirm("Install?", default=True), b"\r") is True

    h2 = Harness()
    assert await h2.feed(h2.prompt.confirm("Install?", default=False), b"\r") is False


@pytest.mark.asyncio
async def test_confirm_reads_explicit_answer() -> None:
    """
    An explicit y/n answer overrides the default.
    """
    h = Harness()
    assert await h.feed(h.prompt.confirm("Install?", default=False), b"y", b"\r") is True


@pytest.mark.asyncio
async def test_choose_returns_selected_index() -> None:
    """
    A numbered selection maps to a zero-based index.
    """
    h = Harness()
    index = await h.feed(h.prompt.choose("Network:", ["a", "b", "c"]), b"2", b"\r")
    assert index == 1
