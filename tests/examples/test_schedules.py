from __future__ import annotations

import asyncio

import httpx
from busylib import types

from examples.schedules.main import (
    SchedulesSettings,
    _minutes_label,
    fetch_bus_arrivals,
    format_arrival_elements,
    parse_args,
    run,
)


def test_settings_load_primary_key_from_env(monkeypatch) -> None:
    """
    Ensure settings read secrets from environment variables.

    The example must avoid hardcoded credentials and use prefixed env keys.
    """
    monkeypatch.setenv("BUSYBAR_SCHEDULES_PRIMARY_KEY", "demo-key")

    settings = SchedulesSettings()

    assert settings.primary_key == "demo-key"


def test_parse_args_allows_stop_override() -> None:
    """
    Ensure CLI stop id has higher priority than env default.

    This keeps one-off runs easy without changing the environment.
    """
    settings = SchedulesSettings(
        primary_key="demo-key",
        stop_id="ENV_STOP",
    )

    args = parse_args(settings, ["--stop-id", "CLI_STOP"])

    assert args.stop_id == "CLI_STOP"


def test_parse_args_reads_token_and_optional_addr() -> None:
    """
    Ensure Busy Bar connection args support token and optional addr.

    The example should allow running without explicit address and still
    accept token override from CLI.
    """
    settings = SchedulesSettings(
        primary_key="demo-key",
        addr=None,
        token=None,
    )

    args = parse_args(settings, ["--token", "demo-token"])

    assert args.addr is None
    assert args.token == "demo-token"


def test_format_arrival_elements_sorts_and_formats_eta() -> None:
    """
    Ensure arrival entries are ordered by time and mapped to display labels.

    The first bus with less than one minute must render as `due`.
    """
    arrivals = [
        {
            "lineName": "42",
            "destinationName": "Center",
            "timeToStation": 180,
        },
        {
            "lineName": "10",
            "destinationName": "Station",
            "timeToStation": 20,
        },
    ]

    elements = format_arrival_elements(
        arrivals,
        display=types.DisplayName.FRONT,
    )

    assert len(elements) == 6
    assert elements[0].id == "route_0"
    assert elements[0].text == "10"
    assert elements[2].id == "mins_0"
    assert elements[2].text == "due"
    assert elements[5].id == "mins_1"
    assert elements[5].text == "3min"


def test_minutes_label_rounds_up() -> None:
    """
    Ensure ETA formatter rounds values to the next full minute.

    This keeps arrival display consistent with short countdown rules.
    """
    assert _minutes_label(60) == "1min"
    assert _minutes_label(61) == "2min"


def test_run_returns_error_without_primary_key(monkeypatch) -> None:
    """
    Ensure run fails fast when TfL key is not configured.

    Missing credentials should produce a non-zero status without network calls.
    """
    monkeypatch.delenv("BUSYBAR_SCHEDULES_PRIMARY_KEY", raising=False)

    result = run([])

    assert result == 1


def test_fetch_bus_arrivals_uses_async_httpx_client() -> None:
    """
    Ensure arrival loading works with async httpx transport abstraction.

    The request should keep bearer auth header and parse list payload shape.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer demo-key"
        assert request.url.path == "/StopPoint/490004733C/Arrivals"
        return httpx.Response(
            status_code=200,
            json=[
                {
                    "lineName": "25",
                    "destinationName": "City",
                    "timeToStation": 120,
                }
            ],
        )

    transport = httpx.MockTransport(responder)

    async def run_case() -> list[dict[str, object]]:
        """
        Execute one fetch call with injected async client.

        The nested runner keeps the test synchronous while exercising awaitable
        transport flow in production-like code path.
        """
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetch_bus_arrivals(
                stop_id="490004733C",
                primary_key="demo-key",
                timeout_sec=1.0,
                client=client,
            )

    arrivals = asyncio.run(run_case())

    assert arrivals == [
        {
            "lineName": "25",
            "destinationName": "City",
            "timeToStation": 120,
        }
    ]
