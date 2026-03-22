"""Integration tests for API endpoints using FastAPI TestClient."""

import pytest

try:
    from app.main import app
    from fastapi.testclient import TestClient
    HAS_APP = True
except (ImportError, ModuleNotFoundError):
    HAS_APP = False

from app.data.store import odds_store

pytestmark = pytest.mark.skipif(not HAS_APP, reason="FastAPI app requires anthropic/strands SDK")


@pytest.fixture(autouse=True)
def reset_store():
    """Ensure each test starts with sample data."""
    odds_store.reset()
    yield
    odds_store.reset()


@pytest.fixture
def client():
    return TestClient(app)


# ─── Health ─────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_200(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"

    def test_health_shows_data_status(self, client):
        res = client.get("/health")
        data = res.json()
        assert "data_loaded" in data
        assert "games_count" in data
        assert data["data_loaded"] is True
        assert data["games_count"] > 0


# ─── Data API ───────────────────────────────────────────────────────────────────

class TestDataAPI:
    def test_list_games(self, client):
        res = client.get("/api/data/games")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] > 0
        assert len(data["games"]) == data["count"]

    def test_list_sportsbooks(self, client):
        res = client.get("/api/data/sportsbooks")
        assert res.status_code == 200
        data = res.json()
        assert len(data["sportsbooks"]) > 0

    def test_get_game_odds(self, client):
        games = client.get("/api/data/games").json()["games"]
        game_id = games[0]["game_id"]
        res = client.get(f"/api/data/games/{game_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["game_id"] == game_id
        assert data["count"] > 0

    def test_get_game_odds_with_sportsbook_filter(self, client):
        games = client.get("/api/data/games").json()["games"]
        game_id = games[0]["game_id"]
        res = client.get(f"/api/data/games/{game_id}?sportsbook=DraftKings")
        assert res.status_code == 200
        data = res.json()
        for record in data["records"]:
            assert record["sportsbook"] == "DraftKings"

    def test_get_nonexistent_game_404(self, client):
        res = client.get("/api/data/games/nonexistent_game_id")
        assert res.status_code == 404

    def test_get_metadata(self, client):
        res = client.get("/api/data/metadata")
        assert res.status_code == 200

    def test_upload_valid_data(self, client):
        payload = {
            "odds": [
                {
                    "game_id": "test_game_1",
                    "sportsbook": "TestBook",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "markets": {"moneyline": {"home": -110, "away": -110}},
                    "last_updated": "2026-03-20T12:00:00Z",
                }
            ]
        }
        res = client.post("/api/data/upload", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "Loaded 1" in data["message"]

    def test_upload_empty_data_400(self, client):
        res = client.post("/api/data/upload", json={"odds": []})
        assert res.status_code == 400

    def test_upload_missing_fields_400(self, client):
        res = client.post("/api/data/upload", json={"odds": [{"game_id": "x"}]})
        assert res.status_code == 400

    def test_reset_data(self, client):
        res = client.post("/api/data/reset")
        assert res.status_code == 200
        data = res.json()
        assert data["records"] > 0


# ─── Briefing API ───────────────────────────────────────────────────────────────

class TestBriefingAPI:
    def test_status_idle_initially(self, client):
        res = client.get("/api/briefing/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("idle", "ready")  # May have a prior briefing

    def test_latest_404_when_no_briefing(self, client):
        """If no briefing has been generated, latest returns 404."""
        from app.agent.odds_agent import odds_agent
        # Clear any existing briefing
        with odds_agent._lock:
            saved = odds_agent._last_briefing
            odds_agent._last_briefing = None
        try:
            res = client.get("/api/briefing/latest")
            assert res.status_code == 404
        finally:
            with odds_agent._lock:
                odds_agent._last_briefing = saved

    def test_evaluate_404_when_no_briefing(self, client):
        from app.agent.odds_agent import odds_agent
        with odds_agent._lock:
            saved = odds_agent._last_briefing
            odds_agent._last_briefing = None
        try:
            res = client.get("/api/briefing/evaluate")
            assert res.status_code == 404
        finally:
            with odds_agent._lock:
                odds_agent._last_briefing = saved


# ─── Chat API ───────────────────────────────────────────────────────────────────

class TestChatAPI:
    def test_empty_message_400(self, client):
        res = client.post("/api/chat", json={"message": "   ", "stream": False})
        assert res.status_code == 400

    def test_message_too_long_422(self, client):
        res = client.post("/api/chat", json={"message": "x" * 5001, "stream": False})
        assert res.status_code == 422
