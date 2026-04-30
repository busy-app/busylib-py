from __future__ import annotations

from collections.abc import Iterable

from examples.hltv_live.hltv_api import LiveMatch, parse_live_matches


def fetch_live_matches() -> list[LiveMatch]:
    """
    Получить live-матчи через python-hltv.

    Оборачивает библиотеку HLTV и приводит данные к моделям LiveMatch.
    """
    try:
        from HLTV import get_live_matches
    except Exception as exc:  # pragma: no cover - зависит от внешнего пакета
        raise RuntimeError("python-hltv не установлен или недоступен") from exc

    raw_matches = get_live_matches()
    if not isinstance(raw_matches, list):
        return []
    normalized = [_normalize_hltv_match(item) for item in raw_matches]
    return parse_live_matches(normalized, only_live=False)


def parse_hltv_live_matches(
    matches: Iterable[dict[str, object]],
) -> list[LiveMatch]:
    """
    Преобразовать список словарей python-hltv в LiveMatch.

    Функция удобна для тестов и офлайн-обработки.
    """
    normalized = [_normalize_hltv_match(item) for item in matches]
    return parse_live_matches(normalized, only_live=False)


def _normalize_hltv_match(match: dict[str, object]) -> dict[str, object]:
    """
    Привести матч python-hltv к универсальному виду.

    Готовит поля id, teams и счёт под parse_live_matches.
    """
    match_id = _first_int(
        match.get("id"),
        match.get("match_id"),
        match.get("matchId"),
    )
    team_left_name = _first_str(
        match.get("team1"),
        match.get("team1_name"),
        match.get("team1Name"),
    )
    team_right_name = _first_str(
        match.get("team2"),
        match.get("team2_name"),
        match.get("team2Name"),
    )
    team_left_logo = _first_str(
        match.get("team1_logo"),
        match.get("team1Logo"),
        match.get("team1_logo_url"),
    )
    team_right_logo = _first_str(
        match.get("team2_logo"),
        match.get("team2Logo"),
        match.get("team2_logo_url"),
    )
    score_left = _first_int(
        match.get("score1"),
        match.get("team1Score"),
    )
    score_right = _first_int(
        match.get("score2"),
        match.get("team2Score"),
    )

    entry: dict[str, object] = {
        "id": match_id,
        "status": "live",
        "teams": [
            {"name": team_left_name, "logo": team_left_logo},
            {"name": team_right_name, "logo": team_right_logo},
        ],
    }
    if score_left is not None:
        entry["score1"] = score_left
    if score_right is not None:
        entry["score2"] = score_right
    return entry


def _first_int(*values: object) -> int | None:
    """
    Вернуть первое значение, приводимое к int.

    Строки с числом приводятся, пустые значения игнорируются.
    """
    for value in values:
        if value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            try:
                return int(text)
            except ValueError:
                continue
    return None


def _first_str(*values: object) -> str | None:
    """
    Вернуть первую непустую строку.

    Удаляет пробелы по краям и игнорирует пустые строки.
    """
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None
