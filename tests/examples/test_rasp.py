from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from busylib import types

from examples.rasp.main import (
    RaspSettings,
    load_cached_schedule,
    arun,
    format_schedule_elements,
    parse_warning_thresholds,
    parse_args,
    save_cached_schedule,
    select_traffic_color,
)
from examples.rasp.yandex_api import (
    YandexRaspPayload,
    YandexRaspSegment,
    fetch_rasp_items,
    find_env_file,
    format_payload,
    normalize_station_code,
)


def test_settings_load_api_key_from_env(monkeypatch) -> None:
    """
    Проверить загрузку ключа Яндекс.Расписаний из env.

    Ключ должен читаться из префиксных переменных, чтобы не хранить
    секрет в исходном коде примера.
    """
    monkeypatch.delenv("BUSYBAR_RASP_DEPARTURE_STATION", raising=False)
    monkeypatch.delenv("BUSYBAR_RASP_DESTINATION_STATION", raising=False)
    monkeypatch.setenv("BUSYBAR_RASP_API_KEY", "demo-key")

    settings = RaspSettings(_env_file=None)

    assert settings.api_key == "demo-key"


def test_parse_args_allows_station_override(monkeypatch) -> None:
    """
    Проверить переопределение станции через CLI.

    Аргумент должен иметь приоритет над значением из настроек.
    """
    monkeypatch.delenv("BUSYBAR_RASP_DEPARTURE_STATION", raising=False)
    monkeypatch.delenv("BUSYBAR_RASP_DESTINATION_STATION", raising=False)
    settings = RaspSettings(
        _env_file=None,
        api_key="demo-key",
        departure_station="s111",
    )

    args = parse_args(settings, ["--departure-station", "s222"])

    assert args.departure_station == "s222"


def test_parse_args_supports_short_flags(monkeypatch) -> None:
    """
    Проверить короткие CLI-аргументы API-клиента.

    Пользователь должен иметь возможность указывать ключ и станции
    короткими флагами `-k`, `-f`, `-t` в основном CLI.
    """
    monkeypatch.delenv("BUSYBAR_RASP_DEPARTURE_STATION", raising=False)
    monkeypatch.delenv("BUSYBAR_RASP_DESTINATION_STATION", raising=False)
    settings = RaspSettings(
        _env_file=None,
        api_key=None,
        departure_station="s111",
    )

    args = parse_args(
        settings,
        ["-k", "demo-key", "-f", "s9600213", "-t", "c213"],
    )

    assert args.api_key == "demo-key"
    assert args.departure_station == "s9600213"
    assert args.destination_station == "c213"


def test_find_env_file_walks_up_directories(tmp_path: Path) -> None:
    """
    Проверить поиск `.env` вверх от директории модуля.

    Функция должна находить ближайший `.env` в родительских каталогах,
    чтобы настройки примера подхватывались без явного экспорта env.
    """
    project_root = tmp_path / "project"
    code_dir = project_root / "examples" / "rasp"
    code_dir.mkdir(parents=True)
    env_file = project_root / ".env"
    env_file.write_text("BUSYBAR_RASP_API_KEY=demo\\n", encoding="utf-8")

    result = find_env_file(code_dir)

    assert result == env_file


def test_normalize_station_code_accepts_station_and_city_codes() -> None:
    """
    Проверить валидацию station/city code для CLI значений.

    Нормализатор должен принимать префиксы `s` и `c`, а также переводить
    регистр к нижнему.
    """
    assert normalize_station_code("S9600213", field_name="code") == "s9600213"
    assert normalize_station_code("c213", field_name="code") == "c213"


def test_fetch_rasp_items_uses_station_endpoint_for_single_station() -> None:
    """
    Проверить формирование параметров запроса к API Яндекса.

    Пример должен передавать обязательные и пользовательские фильтры,
    а затем извлекать список `schedule` из ответа.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3.0/schedule/"
        assert request.url.params["apikey"] == "demo-key"
        assert request.url.params["station"] == "s9600213"
        assert request.url.params["event"] == "departure"
        assert request.url.params["transport_types"] == "bus"
        return httpx.Response(
            status_code=200,
            json={
                "schedule": [
                    {
                        "thread": {"number": "42", "short_title": "Center"},
                        "departure": "2026-02-19T12:00:00+03:00",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(responder)

    async def run_case() -> list[dict[str, object]]:
        """
        Выполнить один асинхронный вызов загрузки расписания.

        В тесте используется подмененный transport, чтобы изолировать
        логику от реальной сети и проверить только клиентский код.
        """
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetch_rasp_items(
                api_key="demo-key",
                departure_station="s9600213",
                destination_station=None,
                event="departure",
                transport_types="bus",
                lang="ru_RU",
                date=None,
                timeout_sec=1.0,
                client=client,
            )

    schedule = asyncio.run(run_case())

    assert len(schedule) == 1
    assert isinstance(schedule[0], YandexRaspSegment)


def test_fetch_rasp_items_uses_search_endpoint_between_stations() -> None:
    """
    Проверить вызов endpoint между станциями при двух кодах станций.

    В этом режиме запрос должен идти на `/v3.0/search/` и извлекать
    данные из списка `segments`.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3.0/search/"
        assert request.url.params["apikey"] == "demo-key"
        assert request.url.params["from"] == "s9600213"
        assert request.url.params["to"] == "c213"
        assert request.url.params["transport_types"] == "bus"
        return httpx.Response(
            status_code=200,
            json={
                "segments": [
                    {
                        "thread": {"number": "100", "short_title": "Express"},
                        "departure": "2026-02-19T12:00:00+03:00",
                        "arrival": "2026-02-19T12:40:00+03:00",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(responder)

    async def run_case() -> list[dict[str, object]]:
        """
        Выполнить тестовый запрос между станциями без реальной сети.

        Используется `MockTransport`, чтобы проверить только сборку
        параметров и разбор структуры ответа.
        """
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetch_rasp_items(
                api_key="demo-key",
                departure_station="s9600213",
                destination_station="c213",
                event="departure",
                transport_types="bus",
                lang="ru_RU",
                date=None,
                timeout_sec=1.0,
                client=client,
            )

    segments = asyncio.run(run_case())

    assert len(segments) == 1
    assert isinstance(segments[0], YandexRaspSegment)


def test_yandex_payload_model_parses_segment_example() -> None:
    """
    Проверить pydantic-модель сегмента Яндекс API на реальном примере.

    Модель должна корректно разобрать вложенные объекты `from`, `to` и
    `thread`, сохранив основные поля для рендера и кеша.
    """
    payload = YandexRaspPayload.model_validate(
        {
            "segments": [
                {
                    "arrival": "23:55:00",
                    "departure": "22:34:00",
                    "start_date": "2026-02-24",
                    "from": {"code": "s9876336", "title": "Славянский Бульвар"},
                    "to": {"code": "s9602011", "title": "Тучково"},
                    "thread": {
                        "number": "6297",
                        "short_title": "Дмитров — Бородино",
                    },
                }
            ]
        }
    )

    assert payload.segments is not None
    assert payload.segments[0].thread is not None
    assert payload.segments[0].thread.number == "6297"
    assert payload.segments[0].from_station is not None
    assert payload.segments[0].from_station.code == "s9876336"


def test_cache_roundtrip_reads_saved_segments(tmp_path: Path) -> None:
    """
    Проверить сохранение и чтение файлового кэша расписания.

    После записи кэша загрузчик должен вернуть те же сегменты, если
    маршрутные параметры и дата запроса совпадают.
    """
    cache_path = tmp_path / "segments.json"
    items = [
        YandexRaspSegment.model_validate(
            {
                "departure": "22:34:00",
                "start_date": "2026-02-24",
                "thread": {"number": "6297", "short_title": "Дмитров — Бородино"},
            }
        )
    ]

    save_cached_schedule(
        cache_path,
        departure_station="s9876336",
        destination_station="s9602011",
        event="departure",
        reference_date="2026-02-24",
        items=items,
    )

    loaded = load_cached_schedule(
        cache_path,
        departure_station="s9876336",
        destination_station="s9602011",
        event="departure",
        reference_date="2026-02-24",
    )

    assert len(loaded) == 1
    assert loaded[0].thread is not None
    assert loaded[0].thread.number == "6297"


def test_format_payload_returns_pretty_json() -> None:
    """
    Проверить человекочитаемое форматирование JSON-ответа API.

    Форматтер должен возвращать строку с отступами и стабильным порядком
    ключей для удобного просмотра ответа в консоли.
    """
    text = format_payload({"b": 2, "a": {"x": 1}})

    assert text == '{\n  "a": {\n    "x": 1\n  },\n  "b": 2\n}'


def test_arun_print_only_returns_success(monkeypatch) -> None:
    """
    Проверить режим печати API-ответа без отправки на Busy Bar.

    При `--print-only` раннер должен запрашивать payload, печатать
    форматированный JSON и завершаться с кодом 0.
    """

    async def fake_fetch_rasp_payload(**_kwargs) -> dict[str, object]:
        return {"schedule": [{"thread": {"number": "42"}}]}

    monkeypatch.setenv("BUSYBAR_RASP_DEPARTURE_STATION", "s9600213")
    monkeypatch.setenv("BUSYBAR_RASP_DESTINATION_STATION", "c213")
    monkeypatch.setattr(
        "examples.rasp.main.fetch_rasp_payload",
        fake_fetch_rasp_payload,
    )

    result = asyncio.run(
        arun(
            [
                "-k",
                "demo-key",
                "-f",
                "s9600213",
                "--print-only",
            ]
        )
    )

    assert result == 0


def test_format_schedule_elements_builds_display_payload() -> None:
    """
    Проверить преобразование расписания в элементы дисплея.

    Функция должна отсортировать рейсы и собрать элементы с учетом
    светофора и окна видимости по оставшемуся времени.
    """
    now = datetime.now(timezone.utc)
    near = (now + timedelta(minutes=12)).isoformat()
    later = (now + timedelta(minutes=25)).isoformat()

    schedule_items = [
        YandexRaspSegment.model_validate(
            {
                "thread": {"number": "20", "short_title": "North"},
                "departure": later,
            }
        ),
        YandexRaspSegment.model_validate(
            {
                "thread": {"number": "10", "short_title": "South"},
                "departure": near,
            }
        ),
    ]

    elements = format_schedule_elements(
        schedule_items,
        event="departure",
        display=types.DisplayName.FRONT,
        reference_date=None,
        thresholds=(40, 30, 20, 10),
        color_green="#00FF00FF",
        color_yellow="#FFFF00FF",
        color_red="#FF0000FF",
        color_gray="#808080FF",
        max_routes=6,
        page_index=0,
        now_ts=int(now.timestamp()),
    )

    assert len(elements) == 6
    assert elements[0].id == "route_0"
    assert elements[0].text == "10"
    assert elements[2].id == "time_0"
    assert elements[2].text == "12m"
    assert elements[2].color == "#808080FF"
    assert elements[5].id == "time_1"
    assert elements[5].text == "25m"


def test_format_schedule_elements_rotates_pages() -> None:
    """
    Проверить постраничную ротацию ближайших рейсов.

    При одинаковом наборе данных смена `page_index` должна переключать
    показываемую пару рейсов внутри окна из шести ближайших.
    """
    now = datetime.now(timezone.utc)
    items: list[YandexRaspSegment] = []
    for idx, minutes in enumerate((12, 13, 14, 15)):
        items.append(
            YandexRaspSegment.model_validate(
                {
                    "thread": {"number": f"{idx}", "short_title": f"R{idx}"},
                    "departure": (now + timedelta(minutes=minutes)).isoformat(),
                }
            )
        )

    first_page = format_schedule_elements(
        items,
        event="departure",
        display=types.DisplayName.FRONT,
        reference_date=None,
        thresholds=(40, 30, 20, 10),
        color_green="#00FF00FF",
        color_yellow="#FFFF00FF",
        color_red="#FF0000FF",
        color_gray="#808080FF",
        max_routes=6,
        page_index=0,
        now_ts=int(now.timestamp()),
    )
    second_page = format_schedule_elements(
        items,
        event="departure",
        display=types.DisplayName.FRONT,
        reference_date=None,
        thresholds=(40, 30, 20, 10),
        color_green="#00FF00FF",
        color_yellow="#FFFF00FF",
        color_red="#FF0000FF",
        color_gray="#808080FF",
        max_routes=6,
        page_index=1,
        now_ts=int(now.timestamp()),
    )

    assert first_page[0].text == "0"
    assert second_page[0].text == "2"


def test_parse_warning_thresholds_supports_traffic_format() -> None:
    """
    Проверить разбор строки порогов светофора.

    Конфигурация должна содержать четыре целых значения в убывающем
    порядке без пропусков и невалидных символов.
    """
    thresholds = parse_warning_thresholds("40,30,20,10")

    assert thresholds == (40, 30, 20, 10)


def test_select_traffic_color_hides_after_last_threshold() -> None:
    """
    Проверить выбор цвета и скрытие после нижнего порога.

    Если времени осталось меньше либо равно последнему порогу,
    элемент должен исчезать из рендера.
    """
    thresholds = (40, 30, 20, 10)

    assert (
        select_traffic_color(
            41,
            thresholds=thresholds,
            color_green="g",
            color_yellow="y",
            color_red="r",
            color_gray="gray",
        )
        == "g"
    )
    assert (
        select_traffic_color(
            40,
            thresholds=thresholds,
            color_green="g",
            color_yellow="y",
            color_red="r",
            color_gray="gray",
        )
        == "y"
    )
    assert (
        select_traffic_color(
            30,
            thresholds=thresholds,
            color_green="g",
            color_yellow="y",
            color_red="r",
            color_gray="gray",
        )
        == "r"
    )
    assert (
        select_traffic_color(
            20,
            thresholds=thresholds,
            color_green="g",
            color_yellow="y",
            color_red="r",
            color_gray="gray",
        )
        == "gray"
    )
    assert (
        select_traffic_color(
            10,
            thresholds=thresholds,
            color_green="g",
            color_yellow="y",
            color_red="r",
            color_gray="gray",
        )
        is None
    )
