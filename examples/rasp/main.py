from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from collections.abc import Sequence
from datetime import datetime, time as dt_time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from busylib import types
from busylib.client import AsyncBusyBar
from examples.rasp.yandex_api import (
    ENV_FILE,
    YandexRaspSegment,
    fetch_rasp_items,
    fetch_rasp_payload,
    format_payload,
    normalize_station_code,
)


class RaspSettings(BaseSettings):
    """
    Настройки примера Яндекс.Расписаний.

    Значения читаются из переменных окружения с префиксом, чтобы ключи
    и параметры станции не хранились в исходниках.
    """

    addr: str | None = None
    token: str | None = None
    api_key: str | None = None
    departure_station: str = "s9600213"
    destination_station: str | None = None
    event: str = "departure"
    transport_types: str | None = None
    lang: str = "ru_RU"
    date: str | None = None
    app_id: str = "rasp-widget"
    display: types.DisplayName = types.DisplayName.FRONT
    request_timeout_sec: float = 10.0
    warning_thresholds: str = "40,30,20,10"
    color_green: str = "#4CAF50FF"
    color_yellow: str = "#FFC107FF"
    color_red: str = "#F44336FF"
    color_gray: str = "#9E9E9EFF"
    refresh_with_schedule_sec: float = 300.0
    refresh_without_schedule_sec: float = 60.0
    render_tick_sec: float = 10.0
    cache_file: str = "examples/rasp/.cache/segments.json"
    max_routes: int = 6
    rotate_every_sec: float = 5.0

    model_config = SettingsConfigDict(
        env_prefix="BUSYBAR_RASP_",
        env_file=str(ENV_FILE) if ENV_FILE is not None else None,
        extra="ignore",
    )

    @field_validator("departure_station", "destination_station")
    @classmethod
    def _validate_station_code(cls, value: str | None) -> str | None:
        """
        Проверить корректность station/city code в настройках.

        Формат кода должен быть `s...` для станции или `c...` для
        населенного пункта, где после префикса идут цифры.
        """
        if value is None:
            return None
        return normalize_station_code(value, field_name="Station code")


def parse_args(
    settings: RaspSettings,
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    """
    Разобрать аргументы запуска примера.

    Аргументы позволяют переопределить env-настройки без редактирования
    переменных окружения для разовых запусков.
    """
    parser = argparse.ArgumentParser(
        description="Render Yandex Rasp station schedule on Busy Bar.",
    )
    parser.add_argument(
        "-k",
        "--api-key",
        default=settings.api_key,
        help="Yandex Rasp API key.",
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
        "-f",
        "--departure-station",
        default=None,
        help="Departure code override (s... station or c... settlement).",
    )
    parser.add_argument(
        "-t",
        "--destination-station",
        default=None,
        help="Destination code override (s... station or c... settlement).",
    )
    parser.add_argument(
        "--event",
        choices=["departure", "arrival"],
        default=settings.event,
        help="Schedule event type.",
    )
    parser.add_argument(
        "--transport-types",
        default=settings.transport_types,
        help="Transport types filter (optional: bus, suburban, train, ...).",
    )
    parser.add_argument(
        "--date",
        default=settings.date,
        help="Date in ISO format YYYY-MM-DD.",
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
    parser.add_argument(
        "--warning-thresholds",
        default=settings.warning_thresholds,
        help="Comma-separated minutes, e.g. 40,30,20,10.",
    )
    parser.add_argument(
        "--refresh-with-schedule-sec",
        type=float,
        default=settings.refresh_with_schedule_sec,
        help="Data refresh interval when schedule exists.",
    )
    parser.add_argument(
        "--refresh-without-schedule-sec",
        type=float,
        default=settings.refresh_without_schedule_sec,
        help="Data refresh interval when schedule is empty.",
    )
    parser.add_argument(
        "--render-tick-sec",
        type=float,
        default=settings.render_tick_sec,
        help="Render refresh interval for countdown updates.",
    )
    parser.add_argument(
        "--cache-file",
        default=settings.cache_file,
        help="Path to schedule cache file.",
    )
    parser.add_argument(
        "--max-routes",
        type=int,
        default=settings.max_routes,
        help="How many nearest routes to keep in rotation window.",
    )
    parser.add_argument(
        "--rotate-every-sec",
        type=float,
        default=settings.rotate_every_sec,
        help="Seconds before switching to next page of routes.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print formatted API response and skip Busy Bar rendering.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def parse_warning_thresholds(value: str) -> tuple[int, int, int, int]:
    """
    Разобрать и проверить пороги светофора в минутах.

    Ожидается строка из четырех целых чисел в убывающем порядке,
    например `40,30,20,10`.
    """
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("warning thresholds must contain 4 comma-separated values")
    try:
        values = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("warning thresholds must be integers") from exc
    if not all(left > right for left, right in zip(values, values[1:], strict=False)):
        raise ValueError("warning thresholds must be strictly descending")
    return values  # type: ignore[return-value]


def select_traffic_color(
    minutes_left: int,
    *,
    thresholds: tuple[int, int, int, int],
    color_green: str,
    color_yellow: str,
    color_red: str,
    color_gray: str,
) -> str | None:
    """
    Выбрать цвет текста по оставшемуся времени.

    После нижнего порога запись скрывается (`None`), иначе цвет
    выбирается по правилам светофора от зеленого к серому.
    """
    if minutes_left > thresholds[0]:
        return color_green
    if minutes_left > thresholds[1]:
        return color_yellow
    if minutes_left > thresholds[2]:
        return color_red
    if minutes_left > thresholds[3]:
        return color_gray
    return None


class CachedSchedule(BaseModel):
    """
    Файловый кэш расписания для старта без первичного запроса.

    Кэш хранит маршрутные параметры и список ранее полученных рейсов,
    чтобы после перезапуска можно было сразу пересчитать остатки.
    """

    departure_station: str
    destination_station: str | None = None
    event: str
    reference_date: str | None = None
    fetched_at: float
    items: list[YandexRaspSegment]

    model_config = ConfigDict(extra="ignore")


def _resolve_cache_path(value: str) -> Path:
    """
    Преобразовать путь к кэшу в абсолютный `Path`.

    Относительные пути резолвятся от текущей рабочей директории запуска.
    """
    return Path(value).expanduser().resolve()


def load_cached_schedule(
    cache_file: Path,
    *,
    departure_station: str,
    destination_station: str | None,
    event: str,
    reference_date: str | None,
) -> list[YandexRaspSegment]:
    """
    Загрузить кэш расписания для текущего запроса.

    Если параметры маршрута не совпадают с текущим запуском,
    кэш игнорируется.
    """
    if not cache_file.is_file():
        return []
    try:
        raw_data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    try:
        cached = CachedSchedule.model_validate(raw_data)
    except Exception:
        return []

    if cached.departure_station != departure_station:
        return []
    if cached.destination_station != destination_station:
        return []
    if cached.event != event:
        return []
    if cached.reference_date != reference_date:
        return []
    return cached.items


def save_cached_schedule(
    cache_file: Path,
    *,
    departure_station: str,
    destination_station: str | None,
    event: str,
    reference_date: str | None,
    items: list[YandexRaspSegment],
) -> None:
    """
    Сохранить кэш расписания в файл.

    Сохраняется только валидированная структура, чтобы последующее чтение
    не требовало дополнительной очистки данных.
    """
    payload = CachedSchedule(
        departure_station=departure_station,
        destination_station=destination_station,
        event=event,
        reference_date=reference_date,
        fetched_at=time.time(),
        items=items,
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        payload.model_dump_json(indent=2, by_alias=True),
        encoding="utf-8",
    )


def _read_event_seconds(
    segment: YandexRaspSegment,
    *,
    event_key: str,
    reference_date: str | None,
) -> int:
    """
    Преобразовать время события в unix timestamp.

    Поддерживаются как ISO datetime, так и формат `HH:MM:SS` из Яндекс API.
    Для time-only значений используется `start_date` записи или reference date.
    """
    value = segment.arrival if event_key == "arrival" else segment.departure
    if value is None or value == "":
        return 0

    normalized = value.replace("Z", "+00:00")
    if "T" in normalized:
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return 0
        return int(dt.timestamp())

    date_source = segment.start_date or reference_date
    if date_source is None:
        date_source = datetime.now().date().isoformat()
    try:
        base_date = datetime.fromisoformat(date_source).date()
    except ValueError:
        return 0
    try:
        parsed_time = dt_time.fromisoformat(normalized)
    except ValueError:
        return 0

    dt = datetime.combine(base_date, parsed_time)
    return int(dt.timestamp())


def format_schedule_elements(
    schedule_items: list[YandexRaspSegment],
    *,
    event: str,
    display: types.DisplayName,
    reference_date: str | None,
    thresholds: tuple[int, int, int, int],
    color_green: str,
    color_yellow: str,
    color_red: str,
    color_gray: str,
    max_routes: int,
    page_index: int,
    page_size: int = 2,
    now_ts: int | None = None,
) -> list[types.TextElement]:
    """
    Преобразовать расписание в элементы для дисплея Busy Bar.

    Берутся ближайшие две записи, для каждой показываются номер рейса,
    направление и обратный отсчет с цветом по порогам.
    """
    event_key = "arrival" if event == "arrival" else "departure"
    now_value = int(datetime.now().timestamp()) if now_ts is None else now_ts
    upcoming: list[tuple[int, YandexRaspSegment]] = []
    for item in schedule_items:
        event_ts = _read_event_seconds(
            item,
            event_key=event_key,
            reference_date=reference_date,
        )
        if event_ts <= 0:
            continue
        upcoming.append((event_ts, item))

    upcoming.sort(key=lambda pair: pair[0])
    elements: list[types.TextElement] = []
    base_y = 2
    line_height = 7

    visible: list[tuple[int, YandexRaspSegment, str, str]] = []
    for event_ts, item in upcoming:
        minutes_left = max(0, math.ceil((event_ts - now_value) / 60))
        color = select_traffic_color(
            minutes_left,
            thresholds=thresholds,
            color_green=color_green,
            color_yellow=color_yellow,
            color_red=color_red,
            color_gray=color_gray,
        )
        if color is None:
            continue
        visible.append((minutes_left, item, color, f"{minutes_left}m"))

    window = visible[: max(1, max_routes)]
    pages_count = max(1, math.ceil(len(window) / page_size))
    page = page_index % pages_count
    start = page * page_size
    page_items = window[start : start + page_size]

    for idx, (_, item, color, label) in enumerate(page_items):
        y = base_y + idx * line_height
        thread = item.thread
        route = thread.number if thread is not None and thread.number else "??"
        if thread is not None and thread.short_title:
            destination = thread.short_title
        elif thread is not None and thread.title:
            destination = thread.title
        else:
            destination = "Unknown"
        eta = label

        elements.extend(
            [
                types.TextElement(
                    id=f"route_{idx}",
                    align="top_mid",
                    x=6,
                    y=y,
                    text=route,
                    font="small",
                    color=color,
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
                    color=color,
                    width=40,
                    scroll_rate=400,
                    display=display,
                ),
                types.TextElement(
                    id=f"time_{idx}",
                    align="top_mid",
                    x=65,
                    y=y,
                    text=eta,
                    font="small",
                    color=color,
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
    Отправить сформированные элементы на Busy Bar.

    Функция упаковывает элементы в `DisplayElements` и вызывает
    один запрос отрисовки через клиент библиотеки.
    """
    payload = types.DisplayElements(
        app_id=app_id,
        elements=elements,
    )
    response = await client.draw_on_display(payload)
    print(f"Draw result: {response.result}")


async def arun(argv: Sequence[str] | None = None) -> int:
    """
    Выполнить один цикл загрузки и рендера расписания.

    Раннер читает настройки, загружает расписание станции и выводит
    ближайшие рейсы на выбранный экран устройства.
    """
    settings = RaspSettings()
    args = parse_args(settings, argv=argv)

    api_key = args.api_key or settings.api_key
    if api_key is None:
        print("Missing BUSYBAR_RASP_API_KEY in environment.")
        return 1

    try:
        thresholds = parse_warning_thresholds(args.warning_thresholds)
        if args.max_routes < 1:
            raise ValueError("max-routes must be >= 1")
        if args.rotate_every_sec <= 0:
            raise ValueError("rotate-every-sec must be > 0")
        departure_station = normalize_station_code(
            args.departure_station or settings.departure_station,
            field_name="Departure station",
        )
        destination_station = (
            normalize_station_code(
                args.destination_station,
                field_name="Destination station",
            )
            if args.destination_station is not None
            else settings.destination_station
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    if args.print_only:
        payload = await fetch_rasp_payload(
            api_key=api_key,
            departure_station=departure_station,
            destination_station=destination_station,
            event=args.event,
            transport_types=args.transport_types,
            lang=settings.lang,
            date=args.date,
            timeout_sec=settings.request_timeout_sec,
        )
        if payload is None:
            return 1
        print(format_payload(payload))
        return 0

    cache_path = _resolve_cache_path(args.cache_file)
    cached_schedule = load_cached_schedule(
        cache_path,
        departure_station=departure_station,
        destination_station=destination_station,
        event=args.event,
        reference_date=args.date,
    )

    async with AsyncBusyBar(addr=args.addr, token=args.token) as client:
        next_fetch_at = (
            time.monotonic() + args.refresh_with_schedule_sec
            if cached_schedule
            else 0.0
        )
        last_render_signature: tuple[str, ...] | None = None
        while True:
            now_mono = time.monotonic()
            if now_mono >= next_fetch_at:
                fetched_items = await fetch_rasp_items(
                    api_key=api_key,
                    departure_station=departure_station,
                    destination_station=destination_station,
                    event=args.event,
                    transport_types=args.transport_types,
                    lang=settings.lang,
                    date=args.date,
                    timeout_sec=settings.request_timeout_sec,
                )
                if fetched_items:
                    cached_schedule = fetched_items
                    try:
                        save_cached_schedule(
                            cache_path,
                            departure_station=departure_station,
                            destination_station=destination_station,
                            event=args.event,
                            reference_date=args.date,
                            items=cached_schedule,
                        )
                    except OSError as exc:
                        print(f"Failed to save cache: {exc}")
                next_fetch_at = now_mono + (
                    args.refresh_with_schedule_sec
                    if cached_schedule
                    else args.refresh_without_schedule_sec
                )

            rotation_index = int(now_mono // args.rotate_every_sec)
            elements = format_schedule_elements(
                cached_schedule,
                event=args.event,
                display=types.DisplayName(args.display),
                reference_date=args.date,
                thresholds=thresholds,
                color_green=settings.color_green,
                color_yellow=settings.color_yellow,
                color_red=settings.color_red,
                color_gray=settings.color_gray,
                max_routes=args.max_routes,
                page_index=rotation_index,
            )
            render_signature = tuple(
                f"{element.id}:{element.text}:{element.color}"
                for element in elements
            )
            if render_signature != last_render_signature:
                if elements:
                    await send_to_display(
                        client=client,
                        app_id=args.app_id,
                        elements=elements,
                    )
                else:
                    await client.clear_display()
                    print("No visible routes in configured warning window.")
                last_render_signature = render_signature
            await asyncio.sleep(args.render_tick_sec)
    return 0


def run(argv: Sequence[str] | None = None) -> int:
    """
    Запустить асинхронный раннер из синхронного контекста.

    Обертка нужна для совместимости с `python -m ...` и тестами,
    которые ожидают синхронную точку входа.
    """
    return asyncio.run(arun(argv))


def main() -> None:
    """
    Точка входа CLI для примера `examples.rasp`.

    Функция завершает процесс кодом возврата раннера.
    """
    raise SystemExit(run())


if __name__ == "__main__":
    main()
