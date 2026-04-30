from __future__ import annotations

import argparse
import asyncio
import math
from collections.abc import Sequence

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from busylib import types
from busylib.client import AsyncBusyBar


class SchedulesSettings(BaseSettings):
    """
    Runtime configuration for the schedules example.

    Values are loaded from environment variables with a dedicated prefix,
    so users can keep secrets and defaults outside the source code.
    """

    addr: str | None = None
    token: str | None = None
    primary_key: str | None = None
    stop_id: str = "490004733C"
    app_id: str = "bus-widget"
    display: types.DisplayName = types.DisplayName.FRONT
    request_timeout_sec: float = 10.0

    model_config = SettingsConfigDict(
        env_prefix="BUSYBAR_SCHEDULES_",
        extra="ignore",
    )


def parse_args(
    settings: SchedulesSettings,
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    """
    Parse command line arguments for one-shot rendering.

    CLI values can override environment-driven defaults, including stop id
    and Busy Bar connection address.
    """
    parser = argparse.ArgumentParser(
        description="Render upcoming TfL arrivals on Busy Bar.",
    )
    parser.add_argument(
        "--addr",
        default=settings.addr,
        help="Busy Bar base URL (optional, defaults to busylib behavior).",
    )
    parser.add_argument(
        "--token",
        default=settings.token,
        help="Busy Bar token (X-API-Token/Bearer, depending on target).",
    )
    parser.add_argument(
        "--stop-id",
        default=None,
        help="TfL stop id override (e.g. 490004733C).",
    )
    parser.add_argument(
        "--display",
        choices=[display.value for display in types.DisplayName],
        default=settings.display.value,
        help="Target display side.",
    )
    parser.add_argument(
        "--app-id",
        default=settings.app_id,
        help="Application id used in display payload.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


async def fetch_bus_arrivals(
    *,
    stop_id: str,
    primary_key: str,
    timeout_sec: float,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, object]]:
    """
    Load arrivals from TfL for the selected stop.

    The request uses bearer authorization and returns parsed JSON records,
    or an empty list when the remote API is unavailable.
    """
    url = f"https://api.tfl.gov.uk/StopPoint/{stop_id}/Arrivals"
    headers = {"Authorization": f"Bearer {primary_key}"}

    async def _do_request(http_client: httpx.AsyncClient) -> list[dict[str, object]]:
        """
        Execute one TfL request and normalize response records.

        The helper keeps transport-level handling compact while preserving
        explicit status checks and JSON shape validation.
        """
        try:
            response = await http_client.get(
                url,
                headers=headers,
                timeout=timeout_sec,
            )
        except httpx.HTTPError as exc:
            print(f"TfL request failed: {exc}")
            return []

        if response.status_code != 200:
            print(f"TfL API error: {response.status_code} {response.text}")
            return []

        data = response.json()
        if not isinstance(data, list):
            print("TfL API returned unexpected payload.")
            return []

        return [item for item in data if isinstance(item, dict)]

    if client is not None:
        return await _do_request(client)

    try:
        async with httpx.AsyncClient() as http_client:
            return await _do_request(http_client)
    except httpx.HTTPError as exc:
        print(f"TfL client failed: {exc}")
        return []


def _minutes_label(seconds: int) -> str:
    """
    Convert seconds to display-friendly ETA text.

    Values under one minute are rendered as `due`, and larger values are
    rounded up to full minutes.
    """
    if seconds < 60:
        return "due"
    return f"{math.ceil(seconds / 60)}min"


def _read_int(value: object, default: int = 0) -> int:
    """
    Read integer-like values from API payload fields.

    This helper keeps formatting logic robust when TfL returns nulls,
    floats, or stringified numbers.
    """
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def format_arrival_elements(
    arrivals: list[dict[str, object]],
    *,
    display: types.DisplayName,
) -> list[types.TextElement]:
    """
    Transform arrival records into Busy Bar text elements.

    The layout renders up to two nearest buses with route, destination,
    and ETA, preserving the visual spacing from the original demo.
    """
    arrivals_sorted = sorted(
        arrivals,
        key=lambda item: _read_int(item.get("timeToStation"), default=0),
    )

    elements: list[types.TextElement] = []
    base_y = 2
    line_height = 7

    for idx, arrival in enumerate(arrivals_sorted[:2]):
        y = base_y + idx * line_height
        route_raw = arrival.get("lineName")
        destination_raw = arrival.get("destinationName")
        seconds = _read_int(arrival.get("timeToStation"), default=0)

        route = route_raw if isinstance(route_raw, str) and route_raw else "??"
        destination = (
            destination_raw
            if isinstance(destination_raw, str) and destination_raw
            else "??"
        )
        eta = _minutes_label(seconds)

        elements.extend(
            [
                types.TextElement(
                    id=f"route_{idx}",
                    align="top_mid",
                    x=6,
                    y=y,
                    text=route,
                    font="small",
                    color="#FFC500FF",
                    width=12,
                    display=display,
                ),
                types.TextElement(
                    id=f"dest_{idx}",
                    align="top_left",
                    x=14,
                    y=y,
                    text=destination,
                    font="small",
                    color="#FFC500FF",
                    width=40,
                    scroll_rate=400,
                    display=display,
                ),
                types.TextElement(
                    id=f"mins_{idx}",
                    align="top_mid",
                    x=65,
                    y=y,
                    text=eta,
                    font="small",
                    color="#FFC500FF",
                    display=display,
                ),
            ]
        )

    return elements


async def send_to_display(
    *,
    client: AsyncBusyBar,
    app_id: str,
    elements: list[types.TextElement],
) -> None:
    """
    Send rendered elements to Busy Bar through busylib client.

    The function builds typed payload and performs one draw request.
    """
    payload = types.DisplayElements(
        app_id=app_id,
        elements=elements,
    )
    response = await client.draw_on_display(payload)
    print(f"Draw result: {response.result}")


async def arun(argv: Sequence[str] | None = None) -> int:
    """
    Execute the schedules example once.

    The runner reads settings, resolves CLI overrides, fetches TfL arrivals,
    and renders resulting lines on the selected Busy Bar display.
    """
    settings = SchedulesSettings()
    args = parse_args(settings, argv=argv)

    primary_key = settings.primary_key
    if primary_key is None:
        print("Missing BUSYBAR_SCHEDULES_PRIMARY_KEY in environment.")
        return 1

    stop_id = args.stop_id or settings.stop_id
    display = types.DisplayName(args.display)

    arrivals = await fetch_bus_arrivals(
        stop_id=stop_id,
        primary_key=primary_key,
        timeout_sec=settings.request_timeout_sec,
    )
    if not arrivals:
        print("No arrivals available.")
        return 0

    elements = format_arrival_elements(
        arrivals,
        display=display,
    )
    if not elements:
        print("No drawable elements were generated.")
        return 0

    async with AsyncBusyBar(addr=args.addr, token=args.token) as client:
        await send_to_display(
            client=client,
            app_id=args.app_id,
            elements=elements,
        )
    return 0


def run(argv: Sequence[str] | None = None) -> int:
    """
    Execute async schedules flow in a sync-friendly wrapper.

    This adapter keeps compatibility with existing tests and CLI entrypoints.
    """
    return asyncio.run(arun(argv))


def main() -> None:
    """
    Provide module entrypoint for CLI execution.

    This wrapper exits with the status code returned by the runner.
    """
    raise SystemExit(run())


if __name__ == "__main__":
    main()
