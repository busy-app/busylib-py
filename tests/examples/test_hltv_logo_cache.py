from examples.hltv_live import hltv_api
from examples.hltv_live import logo_cache


def test_build_logo_filename_uses_id() -> None:
    """
    Убедиться, что при наличии id используется стабильное имя.
    """
    team = hltv_api.HltvTeam(id=42, name="Alpha")
    assert logo_cache._build_logo_filename(team) == "team_42.png"


def test_build_logo_filename_sanitizes_name() -> None:
    """
    Убедиться, что имя команды приводится к безопасному виду.
    """
    team = hltv_api.HltvTeam(name="Very Long Name!!")
    assert logo_cache._build_logo_filename(team).startswith("very-long-name")
