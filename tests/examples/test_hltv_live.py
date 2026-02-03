from examples.hltv_live import hltv_api


def test_parse_live_matches_filters_live() -> None:
    """
    Убедиться, что по умолчанию выбираются только live-матчи.

    Live определяется через статус и булевы флаги.
    """
    payload = [
        {
            "id": 101,
            "status": "LIVE",
            "score": "12-8",
            "teams": [
                {"id": 1, "name": "Alpha", "logo": "https://a/logo.png"},
                {"id": 2, "name": "Beta", "logo": "https://b/logo.png"},
            ],
        },
        {
            "id": 102,
            "status": "scheduled",
            "score1": 0,
            "score2": 0,
            "teams": [
                {"id": 3, "name": "Gamma", "logo": "https://g/logo.png"},
                {"id": 4, "name": "Delta", "logo": "https://d/logo.png"},
            ],
        },
    ]

    matches = hltv_api.parse_live_matches(payload)

    assert len(matches) == 1
    match = matches[0]
    assert match.match_id == 101
    assert match.team_left.name == "Alpha"
    assert match.team_right.name == "Beta"
    assert match.score_left == 12
    assert match.score_right == 8


def test_parse_live_matches_allows_non_live() -> None:
    """
    Убедиться, что флаг only_live отключает фильтр.

    При этом счёт берётся из числовых полей.
    """
    payload = [
        {
            "id": 201,
            "live": False,
            "score1": 1,
            "score2": 2,
            "teams": [
                {"name": "Left", "logo": "https://l/logo.png"},
                {"name": "Right", "logo": "https://r/logo.png"},
            ],
        }
    ]

    matches = hltv_api.parse_live_matches(payload, only_live=False)

    assert len(matches) == 1
    match = matches[0]
    assert match.score_left == 1
    assert match.score_right == 2
