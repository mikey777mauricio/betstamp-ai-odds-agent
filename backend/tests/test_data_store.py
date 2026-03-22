"""Test the odds data store — loading, querying, replacing data."""

import pytest
from app.data.store import OddsStore


@pytest.fixture
def store():
    """Fresh store instance loaded with sample data."""
    return OddsStore()


class TestOddsStore:
    def test_loads_sample_data(self, store):
        odds = store.get_all_odds()
        assert len(odds) == 80  # 10 games x 8 books

    def test_get_games(self, store):
        games = store.get_games()
        assert len(games) == 10

    def test_game_structure(self, store):
        games = store.get_games()
        for g in games:
            assert "game_id" in g
            assert "sport" in g
            assert "home_team" in g
            assert "away_team" in g
            assert "commence_time" in g

    def test_get_odds_for_game(self, store):
        odds = store.get_odds_for_game("nba_20260320_lal_bos")
        assert len(odds) == 8  # 8 sportsbooks

    def test_get_odds_for_game_with_book_filter(self, store):
        odds = store.get_odds_for_game(
            "nba_20260320_lal_bos", sportsbook="DraftKings"
        )
        assert len(odds) == 1
        assert odds[0]["sportsbook"] == "DraftKings"

    def test_get_sportsbooks(self, store):
        books = store.get_sportsbooks()
        assert len(books) == 8
        assert "Pinnacle" in books
        assert "DraftKings" in books

    def test_load_new_data(self, store):
        new_data = {
            "odds": [
                {
                    "game_id": "test_game",
                    "sport": "NBA",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "commence_time": "2026-01-01T00:00:00Z",
                    "sportsbook": "TestBook",
                    "markets": {},
                    "last_updated": "2026-01-01T00:00:00Z",
                }
            ]
        }
        store.load_data(new_data)
        assert len(store.get_all_odds()) == 1
        assert store.get_games()[0]["game_id"] == "test_game"

    def test_reset(self, store):
        store.load_data({"odds": []})
        assert len(store.get_all_odds()) == 0
        store.reset()
        assert len(store.get_all_odds()) == 80

    def test_nonexistent_game(self, store):
        odds = store.get_odds_for_game("nonexistent")
        assert odds == []

    def test_metadata(self, store):
        meta = store.metadata
        assert "description" in meta
        assert "generated" in meta
