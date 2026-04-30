from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from busylib.client import AsyncBusyBar

from examples.bc.client_factory import build_client
from examples.bc.logging_config import configure_logging
from examples.bc.runner import AsyncRunner

from examples.hltv_live.hltv_client import fetch_live_matches
from examples.hltv_live.logo_cache import LogoCache
from examples.hltv_live.rendering import build_match_elements, build_placeholder_elements
from examples.hltv_live.rotation import LiveMatchRotator

APP_ID = "hltv-live"

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """
    Разобрать аргументы командной строки.

    Поддерживает параметры подключения, интервалов и рендера.
    """
    parser = argparse.ArgumentParser(description="HLTV live matches on BusyBar.")
    parser.add_argument(
        "--addr",
        default=os.getenv("BUSY_ADDR", "http://10.0.4.20"),
        help="BusyBar address.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("BUSY_TOKEN"),
        help="Bearer token.",
    )
    parser.add_argument(
        "--app-id",
        default=APP_ID,
        help="App id for assets.",
    )
    parser.add_argument(
        "--display",
        default="front",
        help="Display name: front/back.",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=60.0,
        help="Data refresh interval in seconds.",
    )
    parser.add_argument(
        "--display-seconds",
        type=float,
        default=10.0,
        help="Seconds to show each match.",
    )
    parser.add_argument(
        "--logo-size",
        type=int,
        default=14,
        help="Logo size in pixels.",
    )
    parser.add_argument(
        "--name-length",
        type=int,
        default=9,
        help="Max team name length on display.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--log-file", default=None, help="Log file path.")
    return parser.parse_args()


def run_loop(
    client: AsyncBusyBar,
    runner: AsyncRunner,
    *,
    app_id: str,
    display_name: str,
    refresh_seconds: float,
    display_seconds: float,
    logo_size: int,
    name_length: int,
) -> None:
    """
    Запустить основной цикл рендеринга live-матчей.

    Обновляет данные раз в минуту и переключает матчи каждые 10 секунд.
    """
    rotator = LiveMatchRotator(
        display_seconds=display_seconds,
        refresh_seconds=refresh_seconds,
    )
    logo_cache = LogoCache(
        client,
        runner,
        app_id=app_id,
        logo_size=logo_size,
        timeout_seconds=10.0,
    )
    last_signature: tuple[object, ...] | None = None
    last_message: str | None = None
    error_message: str | None = None

    try:
        while True:
            now = time.monotonic()
            if rotator.should_refresh(now):
                try:
                    matches = fetch_live_matches()
                    error_message = None
                except Exception as exc:  # noqa: BLE001
                    logger.warning("HLTV fetch failed: %s", exc)
                    matches = []
                    error_message = "HLTV недоступен"
                rotator.set_matches(matches, now=now)
                rotator.mark_refreshed(now)
                last_signature = None

            match = rotator.current(now)
            if match is None:
                message = error_message or "Нет live матчей"
                if message != last_message:
                    payload = build_placeholder_elements(
                        message,
                        app_id=app_id,
                        display_name=display_name,
                    )
                    runner.run(client.draw_on_display(payload))
                    last_message = message
                time.sleep(1)
                continue

            left_logo = logo_cache.logo_path_for_team(match.team_left)
            right_logo = logo_cache.logo_path_for_team(match.team_right)
            payload = build_match_elements(
                match,
                app_id=app_id,
                display_name=display_name,
                logo_left_path=left_logo,
                logo_right_path=right_logo,
                logo_size=logo_size,
                name_len=name_length,
            )
            signature = (
                match.match_id,
                match.score_left,
                match.score_right,
                left_logo,
                right_logo,
            )
            if signature != last_signature:
                runner.run(client.draw_on_display(payload))
                last_signature = signature
                last_message = None
            time.sleep(1)
    finally:
        logo_cache.close()


def main() -> None:
    """
    Точка входа для примера live-матчей HLTV.

    Настраивает логирование, подключение и запускает цикл рендера.
    """
    args = parse_args()
    configure_logging(level=args.log_level, log_file=args.log_file)
    client = build_client(args.addr, args.token)
    runner = AsyncRunner()
    try:
        runner.start(client)
        run_loop(
            client,
            runner,
            app_id=args.app_id,
            display_name=args.display,
            refresh_seconds=args.refresh_seconds,
            display_seconds=args.display_seconds,
            logo_size=args.logo_size,
            name_length=args.name_length,
        )
    except KeyboardInterrupt:
        return
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise
    finally:
        try:
            runner.run(client.aclose())
        finally:
            runner.stop()


if __name__ == "__main__":
    main()
