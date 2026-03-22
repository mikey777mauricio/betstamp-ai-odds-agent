"""
In-memory odds data store.

Loads sample data by default. Supports uploading new data via API.
Provides query methods that the agent tools call into.
"""

import json
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

_DATA_DIR = Path(__file__).parent
_SAMPLE_FILE = _DATA_DIR / "sample_odds_data.json"
_ALT_SAMPLE_FILE = _DATA_DIR / "sample_odds_data_alt.json"


class OddsStore:
    """Thread-safe in-memory store for odds records."""

    def __init__(self):
        self._lock = threading.Lock()
        self._odds: list[dict] = []
        self._metadata: dict = {}
        self._load_sample()

    def _load_sample(self):
        with open(_SAMPLE_FILE) as f:
            raw = json.load(f)
        self._metadata = {
            "description": raw.get("description", ""),
            "generated": raw.get("generated", ""),
            "notes": raw.get("notes", []),
        }
        self._odds = raw.get("odds", [])

    def load_data(self, data: dict):
        """Replace the entire dataset with new data."""
        with self._lock:
            self._metadata = {
                "description": data.get("description", "User-uploaded data"),
                "generated": data.get("generated", datetime.now(timezone.utc).isoformat()),
                "notes": data.get("notes", []),
            }
            self._odds = data.get("odds", [])

    def load_alt_sample(self):
        """Load the alternative sample dataset."""
        with self._lock:
            with open(_ALT_SAMPLE_FILE) as f:
                raw = json.load(f)
            self._metadata = {
                "description": raw.get("description", ""),
                "generated": raw.get("generated", ""),
                "notes": raw.get("notes", []),
            }
            self._odds = raw.get("odds", [])

    def reset(self):
        """Reset to sample data."""
        with self._lock:
            self._load_sample()

    @property
    def metadata(self) -> dict:
        return self._metadata.copy()

    def get_all_odds(self) -> list[dict]:
        """Return all odds records."""
        with self._lock:
            return list(self._odds)

    def get_games(self) -> list[dict]:
        """Return unique games with basic info."""
        with self._lock:
            seen = {}
            for record in self._odds:
                gid = record["game_id"]
                if gid not in seen:
                    seen[gid] = {
                        "game_id": gid,
                        "sport": record.get("sport", "unknown"),
                        "home_team": record.get("home_team", "Unknown"),
                        "away_team": record.get("away_team", "Unknown"),
                        "commence_time": record.get("commence_time", ""),
                    }
            return list(seen.values())

    def get_odds_for_game(
        self, game_id: str, sportsbook: Optional[str] = None
    ) -> list[dict]:
        """Return odds records for a specific game, optionally filtered by book."""
        with self._lock:
            results = [r for r in self._odds if r["game_id"] == game_id]
            if sportsbook:
                results = [r for r in results if r["sportsbook"] == sportsbook]
            return results

    def get_sportsbooks(self) -> list[str]:
        """Return list of unique sportsbook names."""
        with self._lock:
            return sorted({r["sportsbook"] for r in self._odds})

    def get_odds_for_sportsbook(self, sportsbook: str) -> list[dict]:
        """Return all odds records for a given sportsbook."""
        with self._lock:
            return [r for r in self._odds if r["sportsbook"] == sportsbook]


# Singleton instance
odds_store = OddsStore()
