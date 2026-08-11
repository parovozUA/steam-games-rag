from pathlib import Path

import pytest

from data_pipeline.csv_games import normalize_row, stream_games

pytestmark = pytest.mark.unit


def test_normalization_calculates_rating_and_cleans_fields():
    game = normalize_row(
        {
            "AppID": "7",
            "Name": "<b>Game</b>",
            "Release date": "Jan 02, 2021",
            "About the game": "<p>Hello &amp; welcome</p>",
            "Supported languages": "['English', 'Ukrainian']",
            "Header image": "javascript:bad",
            "Windows": "True",
            "Positive": "75",
            "Negative": "25",
            "Genres": "Action, RPG",
        },
        100,
    )
    assert game.rating_percent == 75
    assert game.reviews_count == 100
    assert game.release_date.isoformat() == "2021-01-02"
    assert game.about == "Hello & welcome"
    assert game.header_image is None
    assert game.genres == ["Action", "RPG"]
    assert game.payload()["release_date"] == "2021-01-02T00:00:00Z"


def test_zero_reviews_and_duplicates_are_safe():
    fixture = Path(__file__).parent / "fixtures" / "steam_games.csv"
    games = list(stream_games(fixture, 3000))
    assert [game.app_id for game in games] == [10, 20, 30]
    assert games[1].rating_percent is None
    assert games[2].release_date is None
