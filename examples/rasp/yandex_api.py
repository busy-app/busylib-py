from __future__ import annotations

import json
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


def find_env_file(start_dir: Path) -> Path | None:
    """
    Найти `.env`, поднимаясь вверх по директориям.

    Поиск начинается с переданной директории и продолжается до корня,
    чтобы пример подхватывал `.env` из корня проекта без ручного экспорта.
    """
    for directory in (start_dir, *start_dir.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


ENV_FILE = find_env_file(Path(__file__).resolve().parent)


def normalize_station_code(value: str, *, field_name: str) -> str:
    """
    Нормализовать и проверить station/city code из CLI или настроек.

    Поддерживаются коды вида `s9600213` и `c213`. При ошибочном формате
    выбрасывается `ValueError` с пояснением для пользователя.
    """
    normalized = value.strip().lower()
    if len(normalized) < 2:
        raise ValueError(f"{field_name} is too short")
    if normalized[0] not in {"s", "c"} or not normalized[1:].isdigit():
        raise ValueError(
            f"{field_name} must look like s9600213 or c213"
        )
    return normalized


class YandexCarrierCodes(BaseModel):
    """
    Коды перевозчика в различных системах.

    Модель описывает вложенный объект `thread.carrier.codes` из API.
    """

    iata: str | None = None
    icao: str | None = None
    sirena: str | None = None

    model_config = ConfigDict(extra="ignore")


class YandexCarrier(BaseModel):
    """
    Данные перевозчика для рейса.

    Поля отражают объект `thread.carrier` и остаются опциональными,
    так как API может возвращать неполные сведения.
    """

    address: str | None = None
    code: int | None = None
    codes: YandexCarrierCodes | None = None
    contacts: str | None = None
    email: str | None = None
    logo: str | None = None
    logo_svg: str | None = None
    phone: str | None = None
    title: str | None = None
    url: str | None = None

    model_config = ConfigDict(extra="ignore")


class YandexTransportSubtype(BaseModel):
    """
    Подтип транспорта в треде маршрута.

    Используется для расширенных атрибутов рейса (цвет, название и код).
    """

    code: str | None = None
    color: str | None = None
    title: str | None = None

    model_config = ConfigDict(extra="ignore")


class YandexStationRef(BaseModel):
    """
    Краткое описание станции/населенного пункта в API.

    Соответствует объектам `from` и `to` в элементах расписания.
    """

    code: str | None = None
    popular_title: str | None = None
    short_title: str | None = None
    station_type: str | None = None
    station_type_name: str | None = None
    title: str | None = None
    transport_type: str | None = None
    type: str | None = None

    model_config = ConfigDict(extra="ignore")


class YandexThread(BaseModel):
    """
    Тред маршрута, к которому относится запись расписания.

    Содержит номер, название, перевозчика и доп. характеристики рейса.
    """

    carrier: YandexCarrier | None = None
    express_type: str | None = None
    number: str | None = None
    short_title: str | None = None
    thread_method_link: str | None = None
    title: str | None = None
    transport_subtype: YandexTransportSubtype | None = None
    transport_type: str | None = None
    uid: str | None = None
    vehicle: str | None = None

    model_config = ConfigDict(extra="ignore")


class YandexRaspSegment(BaseModel):
    """
    Унифицированная запись расписания/сегмента Яндекс API.

    Модель покрывает поля из `/schedule/` и `/search/`, включая
    вложенные объекты станций и thread.
    """

    arrival: str | None = None
    arrival_platform: str | None = None
    arrival_terminal: str | None = None
    days: str | None = None
    departure: str | None = None
    departure_platform: str | None = None
    departure_terminal: str | None = None
    duration: float | None = None
    except_days: str | None = None
    from_station: YandexStationRef | None = Field(default=None, alias="from")
    start_date: str | None = None
    stops: str | None = None
    thread: YandexThread | None = None
    to_station: YandexStationRef | None = Field(default=None, alias="to")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class YandexRaspPayload(BaseModel):
    """
    Верхнеуровневый payload ответа Яндекс.Расписаний.

    В зависимости от ручки данные могут приходить в `schedule`
    или в `segments`.
    """

    schedule: list[YandexRaspSegment] | None = None
    segments: list[YandexRaspSegment] | None = None

    model_config = ConfigDict(extra="ignore")


def build_request(
    *,
    api_key: str,
    departure_station: str,
    destination_station: str | None,
    event: str,
    transport_types: str | None,
    lang: str,
    date: str | None,
) -> tuple[str, dict[str, str | int], str]:
    """
    Собрать endpoint, параметры запроса и ключ списка результатов.

    Для одной станции используется `/v3.0/schedule/` и список `schedule`.
    Для пары станций используется `/v3.0/search/` и список `segments`.
    """
    if destination_station is not None:
        url = "https://api.rasp.yandex-net.ru/v3.0/search/"
        params: dict[str, str | int] = {
            "apikey": api_key,
            "from": departure_station,
            "to": destination_station,
            "lang": lang,
            "format": "json",
        }
        if transport_types:
            params["transport_types"] = transport_types
        list_key = "segments"
    else:
        url = "https://api.rasp.yandex-net.ru/v3.0/schedule/"
        params = {
            "apikey": api_key,
            "station": departure_station,
            "lang": lang,
            "format": "json",
            "event": event,
        }
        if transport_types:
            params["transport_types"] = transport_types
        list_key = "schedule"

    if date is not None:
        params["date"] = date

    return url, params, list_key


async def fetch_rasp_payload(
    *,
    api_key: str,
    departure_station: str,
    destination_station: str | None,
    event: str,
    transport_types: str | None,
    lang: str,
    date: str | None,
    timeout_sec: float,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object] | None:
    """
    Запросить сырой JSON-ответ Яндекс.Расписаний.

    Возвращает словарь ответа при успешном запросе и `None` при ошибке
    транспорта, не-200 ответе или невалидном JSON-объекте.
    """
    url, params, _ = build_request(
        api_key=api_key,
        departure_station=departure_station,
        destination_station=destination_station,
        event=event,
        transport_types=transport_types,
        lang=lang,
        date=date,
    )

    async def _do_request(http_client: httpx.AsyncClient) -> dict[str, object] | None:
        """
        Выполнить единичный HTTP-запрос и проверить формат ответа.

        Функция валидирует код ответа и тип JSON-пейлоада, чтобы вызывающий
        код работал только с объектом-словарем.
        """
        try:
            response = await http_client.get(
                url,
                params=params,
                timeout=timeout_sec,
            )
        except httpx.HTTPError as exc:
            print(f"Yandex Rasp request failed: {exc}")
            return None

        if response.status_code != 200:
            print(f"Yandex Rasp API error: {response.status_code} {response.text}")
            return None

        try:
            data = response.json()
        except ValueError:
            print("Yandex Rasp API returned non-JSON payload.")
            return None

        if not isinstance(data, dict):
            print("Yandex Rasp API returned unexpected payload.")
            return None
        return data

    if client is not None:
        return await _do_request(client)

    try:
        async with httpx.AsyncClient() as http_client:
            return await _do_request(http_client)
    except httpx.HTTPError as exc:
        print(f"Yandex Rasp client failed: {exc}")
        return None


def parse_rasp_items(
    payload: dict[str, object],
    *,
    list_key: str,
) -> list[YandexRaspSegment]:
    """
    Провалидировать список записей API в pydantic-модели.

    Используется единая схема `YandexRaspSegment`; невалидные записи
    пропускаются с диагностическим сообщением.
    """
    try:
        model = YandexRaspPayload.model_validate(payload)
    except ValidationError as exc:
        print(f"Yandex Rasp payload validation error: {exc}")
        return []

    raw_items = model.segments if list_key == "segments" else model.schedule
    if raw_items is None:
        print(f"Yandex Rasp API response has no {list_key} list.")
        return []
    return raw_items


async def fetch_rasp_items(
    *,
    api_key: str,
    departure_station: str,
    destination_station: str | None,
    event: str,
    transport_types: str | None,
    lang: str,
    date: str | None,
    timeout_sec: float,
    client: httpx.AsyncClient | None = None,
) -> list[YandexRaspSegment]:
    """
    Запросить и нормализовать список записей расписания.

    Функция выбирает `schedule` или `segments` в зависимости от режима
    запроса и возвращает список валидированных `YandexRaspSegment`.
    """
    payload = await fetch_rasp_payload(
        api_key=api_key,
        departure_station=departure_station,
        destination_station=destination_station,
        event=event,
        transport_types=transport_types,
        lang=lang,
        date=date,
        timeout_sec=timeout_sec,
        client=client,
    )
    if payload is None:
        return []

    _, _, list_key = build_request(
        api_key=api_key,
        departure_station=departure_station,
        destination_station=destination_station,
        event=event,
        transport_types=transport_types,
        lang=lang,
        date=date,
    )
    items = parse_rasp_items(payload, list_key=list_key)
    if destination_station is not None and not items:
        print(
            "No route segments found. Try without --transport-types "
            "or choose another date."
        )
    return items


def format_payload(payload: dict[str, object]) -> str:
    """
    Преобразовать JSON-ответ в читаемый текст.

    Форматирование использует отступы и сортировку ключей для удобного
    просмотра ответа в консоли.
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


if __name__ == "__main__":
    print(
        "Use `python -m examples.rasp --print-only` to fetch and print "
        "formatted Yandex Rasp response."
    )
