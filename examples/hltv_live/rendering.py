from __future__ import annotations

from busylib import display, types

from examples.hltv_live.hltv_api import LiveMatch


def shorten_team_name(name: str, max_len: int) -> str:
    """
    Укоротить название команды до заданной длины.

    Удаляет лишние пробелы и обрезает строку без добавления суффиксов.
    """
    text = name.strip()
    if max_len <= 0:
        return ""
    return text if len(text) <= max_len else text[:max_len]


def format_score(value: int | None) -> str:
    """
    Вернуть текстовое представление счёта.

    При отсутствии значения возвращает дефис.
    """
    return str(value) if value is not None else "-"


def build_match_elements(
    match: LiveMatch,
    *,
    app_id: str,
    display_name: str,
    logo_left_path: str | None,
    logo_right_path: str | None,
    logo_size: int,
    name_len: int,
) -> types.DisplayElements:
    """
    Построить элементы отображения для live-матча.

    Делит экран пополам: слева "лого название счёт", справа "счёт название лого".
    """
    spec = display.get_display_spec(display_name)
    half = spec.width // 2
    logo_y = max(0, (spec.height - logo_size) // 2)
    left_name = shorten_team_name(match.team_left.name, name_len)
    right_name = shorten_team_name(match.team_right.name, name_len)
    left_score = format_score(match.score_left)
    right_score = format_score(match.score_right)

    elements: list[types.DisplayElement] = [
        types.TextElement(
            id="left-text",
            x=logo_size + 2,
            y=4,
            text=f"{left_name} {left_score}",
            font="small",
            display=spec.name,
        ),
        types.TextElement(
            id="right-text",
            x=half,
            y=4,
            text=f"{right_score} {right_name}",
            font="small",
            display=spec.name,
        ),
    ]

    if logo_left_path:
        elements.append(
            types.ImageElement(
                id="left-logo",
                x=0,
                y=logo_y,
                path=logo_left_path,
                display=spec.name,
            )
        )
    if logo_right_path:
        elements.append(
            types.ImageElement(
                id="right-logo",
                x=spec.width - logo_size,
                y=logo_y,
                path=logo_right_path,
                display=spec.name,
            )
        )

    return types.DisplayElements(app_id=app_id, elements=elements)


def build_placeholder_elements(
    message: str,
    *,
    app_id: str,
    display_name: str,
) -> types.DisplayElements:
    """
    Построить элементы для состояния без матчей.

    Выводит одно сообщение по центру экрана.
    """
    spec = display.get_display_spec(display_name)
    elements: list[types.DisplayElement] = [
        types.TextElement(
            id="empty",
            x=0,
            y=4,
            text=message,
            font="small",
            display=spec.name,
        )
    ]
    return types.DisplayElements(app_id=app_id, elements=elements)
