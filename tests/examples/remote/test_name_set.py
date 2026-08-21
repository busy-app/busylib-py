from __future__ import annotations

import httpx2
import pytest

from busylib import AsyncBusyBar
from examples.remote.commands.name_set import (
    MAX_NAME_LENGTH,
    NameSetCommand,
    validate_device_name,
)


@pytest.mark.parametrize(
    "name",
    [
        "Front desk",
        "bar-1",
        "A",
        "x" * MAX_NAME_LENGTH,
        "Anna's Busy Bar",
        "!()-_=+;:,.?'|@#$%^&",
        '*[]{}/\\"<>',
    ],
)
def test_validate_device_name_accepts_valid_names(name: str) -> None:
    """
    Accept names within the firmware's allowed character set and length.
    """
    assert validate_device_name(name) is None


@pytest.mark.parametrize(
    "name,expected_error",
    [
        ("", "empty"),
        ("   ", "only of spaces"),
        ("x" * (MAX_NAME_LENGTH + 1), "longer than"),
        ("привет", "illegal character"),
        ("emoji 🚀", "illegal character"),
        ("tab\there", "illegal character"),
    ],
)
def test_validate_device_name_rejects_invalid_names(
    name: str, expected_error: str
) -> None:
    """
    Reject names the firmware itself would reject, with a matching reason.
    """
    error = validate_device_name(name)
    assert error is not None
    assert expected_error in error


def test_validate_device_name_checks_illegal_chars_before_length() -> None:
    """
    Report an illegal character even when the name is also too long.

    Matches the firmware's check order in `device_name_validate()`.
    """
    error = validate_device_name("п" * (MAX_NAME_LENGTH + 1))
    assert error is not None
    assert "illegal character" in error


@pytest.mark.asyncio
async def test_name_set_posts_name_to_device() -> None:
    """
    Send a valid name to POST /api/name and report success.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx2.Response(200, json={"result": "OK"})

    client = AsyncBusyBar(
        addr="http://device.local",
        transport=httpx2.MockTransport(responder),
    )
    messages: list[str] = []
    command = NameSetCommand(client, messages.append)

    handled, error = await command.handle(["Front", "desk"])
    await client.aclose()

    assert handled is True
    assert error is None
    assert seen["path"] == "/api/name"
    assert b"Front desk" in bytes(seen["body"])  # type: ignore[arg-type]
    assert messages[-1] == "name_set: ok Front desk"


@pytest.mark.asyncio
async def test_name_set_rejects_invalid_name_without_calling_device() -> None:
    """
    Fail locally on an invalid name and never touch the API.
    """
    calls: list[str] = []

    def responder(request: httpx2.Request) -> httpx2.Response:
        calls.append(request.url.path)
        return httpx2.Response(200, json={"result": "OK"})

    client = AsyncBusyBar(
        addr="http://device.local",
        transport=httpx2.MockTransport(responder),
    )
    messages: list[str] = []
    command = NameSetCommand(client, messages.append)

    await command.handle(["x" * (MAX_NAME_LENGTH + 1)])
    await client.aclose()

    assert calls == []
    assert "error" in messages[-1]
    assert "longer than" in messages[-1]


@pytest.mark.asyncio
async def test_name_set_reports_api_failure() -> None:
    """
    Surface an API failure as a status message instead of raising.
    """

    def responder(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(403, json={"error": "Forbidden"})

    client = AsyncBusyBar(
        addr="http://device.local",
        transport=httpx2.MockTransport(responder),
    )
    messages: list[str] = []
    command = NameSetCommand(client, messages.append)

    handled, error = await command.handle(["Front desk"])
    await client.aclose()

    assert handled is True
    assert error is None
    assert messages[-1].startswith("name_set: error")
