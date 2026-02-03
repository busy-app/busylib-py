from examples.hltv_live import hltv_client


def test_parse_hltv_live_matches_maps_fields() -> None:
    """
    Убедиться, что поля python-hltv правильно мапятся в LiveMatch.
    """
    matches = [
        {
            "id": 301,
            "team1": "Alpha",
            "team2": "Beta",
            "team1_logo": "https://a/logo.png",
            "team2_logo": "https://b/logo.png",
            "score1": 7,
            "score2": 5,
        }
    ]

    parsed = hltv_client.parse_hltv_live_matches(matches)

    assert len(parsed) == 1
    match = parsed[0]
    assert match.match_id == 301
    assert match.team_left.name == "Alpha"
    assert match.team_right.name == "Beta"
    assert match.score_left == 7
    assert match.score_right == 5


def test_parse_hltv_live_matches_handles_missing_scores() -> None:
    """
    Убедиться, что отсутствие счёта не ломает парсер.
    """
    matches = [
        {
            "match_id": 401,
            "team1_name": "Left",
            "team2_name": "Right",
            "team1Logo": "https://l/logo.png",
            "team2Logo": "https://r/logo.png",
        }
    ]

    parsed = hltv_client.parse_hltv_live_matches(matches)

    assert len(parsed) == 1
    match = parsed[0]
    assert match.score_left is None
    assert match.score_right is None
