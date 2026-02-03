from examples.hltv_live import hltv_api
from examples.hltv_live import rotation


def _match(match_id: int) -> hltv_api.LiveMatch:
    """
    Быстро собрать LiveMatch для тестов ротации.
    """
    return hltv_api.LiveMatch(
        match_id=match_id,
        team_left=hltv_api.HltvTeam(name=f"L{match_id}"),
        team_right=hltv_api.HltvTeam(name=f"R{match_id}"),
        score_left=0,
        score_right=0,
        status="live",
    )


def test_rotator_switches_by_interval() -> None:
    """
    Ротатор должен переключать матч каждые 10 секунд.
    """
    rotator = rotation.LiveMatchRotator(display_seconds=10, refresh_seconds=60)
    rotator.set_matches([_match(1), _match(2), _match(3)], now=0)

    assert rotator.current(0).match_id == 1
    assert rotator.current(9).match_id == 1
    assert rotator.current(10).match_id == 2
    assert rotator.current(20).match_id == 3
    assert rotator.current(30).match_id == 1


def test_rotator_handles_multiple_steps() -> None:
    """
    Ротатор должен корректно перескакивать через несколько интервалов.
    """
    rotator = rotation.LiveMatchRotator(display_seconds=10, refresh_seconds=60)
    rotator.set_matches([_match(1), _match(2), _match(3)], now=0)

    assert rotator.current(25).match_id == 3
    assert rotator.current(45).match_id == 2


def test_rotator_resets_on_match_change() -> None:
    """
    При изменении списка матчей ротация начинается сначала.
    """
    rotator = rotation.LiveMatchRotator(display_seconds=10, refresh_seconds=60)
    rotator.set_matches([_match(1), _match(2)], now=0)
    assert rotator.current(10).match_id == 2

    rotator.set_matches([_match(3), _match(4)], now=100)
    assert rotator.current(100).match_id == 3


def test_rotator_should_refresh() -> None:
    """
    Проверить интервал обновления данных.
    """
    rotator = rotation.LiveMatchRotator(display_seconds=10, refresh_seconds=60)

    assert rotator.should_refresh(0) is True
    rotator.mark_refreshed(0)
    assert rotator.should_refresh(59) is False
    assert rotator.should_refresh(60) is True
