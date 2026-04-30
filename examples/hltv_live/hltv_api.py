from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field


class HltvTeam(BaseModel):
    """
    Команда HLTV из источника с матчами.

    Содержит минимальный набор полей для логотипа и имени.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: int | None = None
    name: str
    logo_url: str | None = Field(default=None, alias="logo")


class LiveMatch(BaseModel):
    """
    Live-матч CS2 с минимальными данными для рендера.

    Хранит команды, счёт и статус для фильтрации.
    """

    model_config = ConfigDict(frozen=True)

    match_id: int
    team_left: HltvTeam
    team_right: HltvTeam
    score_left: int | None = None
    score_right: int | None = None
    status: str | None = None


def parse_live_matches(
    payload: list[dict[str, object]],
    *,
    only_live: bool = True,
) -> list[LiveMatch]:
    """
    Преобразовать JSON-ответ в список live-матчей.

    Поддерживает вариации полей у источников и фильтрует по live-статусу.
    """
    matches: list[LiveMatch] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if only_live and not _is_live_entry(entry):
            continue
        match = _build_match(entry)
        if match is None:
            continue
        matches.append(match)
    return matches


def parse_live_matches_json(
    raw_json: str,
    *,
    only_live: bool = True,
) -> list[LiveMatch]:
    """
    Прочитать JSON-строку и извлечь live-матчи.

    Ожидает массив объектов; некорректный формат даст пустой список.
    """
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return parse_live_matches(payload, only_live=only_live)


def _build_match(entry: dict[str, object]) -> LiveMatch | None:
    """
    Собрать LiveMatch из записи источника.

    Возвращает None, если данных о командах недостаточно.
    """
    match_id = _as_int(entry.get("id"))
    teams = entry.get("teams")
    if match_id is None or not isinstance(teams, list) or len(teams) < 2:
        return None
    left = _build_team(teams[0])
    right = _build_team(teams[1])
    if left is None or right is None:
        return None
    score = _extract_score(entry)
    status = _as_str(entry.get("status"))
    return LiveMatch(
        match_id=match_id,
        team_left=left,
        team_right=right,
        score_left=score[0] if score else None,
        score_right=score[1] if score else None,
        status=status,
    )


def _build_team(entry: object) -> HltvTeam | None:
    """
    Собрать данные команды из словаря источника.

    Требует имя команды; остальные поля опциональны.
    """
    if not isinstance(entry, dict):
        return None
    name = _as_str(entry.get("name")) or _as_str(entry.get("teamName"))
    if not name:
        return None
    data = {
        "id": _as_int(entry.get("id")),
        "name": name,
        "logo": _as_str(entry.get("logo")) or _as_str(entry.get("teamLogo")),
    }
    return HltvTeam.model_validate(data)


def _extract_score(entry: dict[str, object]) -> tuple[int, int] | None:
    """
    Извлечь счёт из записи матча.

    Поддерживает строковые и числовые представления счёта.
    """
    score_1 = _as_int(entry.get("score1"))
    score_2 = _as_int(entry.get("score2"))
    if score_1 is not None and score_2 is not None:
        return score_1, score_2
    score_1 = _as_int(entry.get("team1Score"))
    score_2 = _as_int(entry.get("team2Score"))
    if score_1 is not None and score_2 is not None:
        return score_1, score_2
    score_text = _as_str(entry.get("score"))
    if score_text:
        parsed = _parse_score_text(score_text)
        if parsed:
            return parsed
    return None


def _parse_score_text(text: str) -> tuple[int, int] | None:
    """
    Прочитать счёт из строки вида "13-9" или "13:9".

    Возвращает None при нераспознаваемом формате.
    """
    for separator in ("-", ":"):
        if separator in text:
            left, right = (part.strip() for part in text.split(separator, maxsplit=1))
            left_score = _as_int(left)
            right_score = _as_int(right)
            if left_score is None or right_score is None:
                return None
            return left_score, right_score
    return None


def _is_live_entry(entry: dict[str, object]) -> bool:
    """
    Проверить, помечен ли матч как live.

    Учитывает булевы флаги и статус в строковом виде.
    """
    live_flag = entry.get("live")
    if isinstance(live_flag, bool):
        return live_flag
    status = _as_str(entry.get("status"))
    if status is None:
        return False
    return status.lower() in {"live", "ongoing", "in progress", "inprogress"}


def _as_int(value: object) -> int | None:
    """
    Привести значение к int, если это возможно.

    При ошибке преобразования возвращает None.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _as_str(value: object) -> str | None:
    """
    Привести значение к str, если это строка.

    Пустые строки возвращает как None.
    """
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None
