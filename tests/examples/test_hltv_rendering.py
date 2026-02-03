from examples.hltv_live import hltv_api
from examples.hltv_live import rendering


def test_shorten_team_name_trims() -> None:
    """
    Убедиться, что имя команды обрезается без суффиксов.
    """
    assert rendering.shorten_team_name("  Alpha  ", 5) == "Alpha"
    assert rendering.shorten_team_name("VeryLongName", 4) == "Very"


def test_build_match_elements_layout() -> None:
    """
    Убедиться, что рендер создаёт ожидаемые элементы.
    """
    match = hltv_api.LiveMatch(
        match_id=10,
        team_left=hltv_api.HltvTeam(name="Alpha"),
        team_right=hltv_api.HltvTeam(name="Beta"),
        score_left=12,
        score_right=9,
        status="live",
    )

    payload = rendering.build_match_elements(
        match,
        app_id="hltv",
        display_name="front",
        logo_left_path="alpha.png",
        logo_right_path="beta.png",
        logo_size=14,
        name_len=8,
    )

    assert payload.app_id == "hltv"
    assert len(payload.elements) == 4
    texts = [element for element in payload.elements if element.type == "text"]
    assert any(element.text == "Alpha 12" for element in texts)
    assert any(element.text == "9 Beta" for element in texts)


def test_build_placeholder_elements() -> None:
    """
    Проверить вывод сообщения при отсутствии матчей.
    """
    payload = rendering.build_placeholder_elements(
        "Нет live матчей",
        app_id="hltv",
        display_name="front",
    )

    assert payload.app_id == "hltv"
    assert payload.elements[0].text == "Нет live матчей"
