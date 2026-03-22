"""Strands @tool wrappers for data query operations."""

import logging
from strands import tool

from app.data.store import odds_store
from app.agent.tools.trace import _log_tool_call
from app.tools.analysis_tools import get_market_summary

logger = logging.getLogger(__name__)


@tool
def get_games() -> dict:
    """Get list of all games in the current dataset with basic info (teams, sport, commence time).
    Use this first to understand what games are available for analysis.

    When to use: Always call this first to see the full slate before drilling into specific games.
    """
    _log_tool_call("get_games", {})
    try:
        games = odds_store.get_games()
        if not games:
            logger.warning("get_games returned empty — no data loaded")
            return {"games": [], "count": 0, "warning": "No data loaded. Upload data via /api/data/upload first."}
        return {"games": games, "count": len(games)}
    except Exception as e:
        logger.error(f"get_games failed: {e}", exc_info=True)
        return {"error": str(e), "games": [], "count": 0}


@tool
def get_odds_for_game(game_id: str, sportsbook: str = "") -> dict:
    """Get all odds records for a specific game, optionally filtered by sportsbook.
    Returns spreads, moneylines, and totals from each book.

    When to use: Drill into a specific game's odds across all books, or filter to one book.

    Args:
        game_id: The game identifier (e.g., 'nba_20260320_lal_bos')
        sportsbook: Optional sportsbook name to filter by (e.g., 'DraftKings')
    """
    _log_tool_call("get_odds_for_game", {"game_id": game_id, "sportsbook": sportsbook})
    try:
        book = sportsbook if sportsbook else None
        records = odds_store.get_odds_for_game(game_id, sportsbook=book)
        return {"game_id": game_id, "records": records, "count": len(records)}
    except Exception as e:
        logger.error(f"get_odds_for_game failed: {e}", exc_info=True)
        return {"error": str(e), "game_id": game_id, "records": [], "count": 0}


@tool
def get_market_summary_tool(game_id: str) -> dict:
    """Get a comprehensive market summary for a game including consensus spread,
    total, win probability, and the range across books.

    When to use: Get a quick snapshot of market conditions before deeper analysis.
    For detailed odds comparison across books, use find_best_lines_tool instead.

    Args:
        game_id: The game identifier
    """
    _log_tool_call("get_market_summary", {"game_id": game_id})
    try:
        return get_market_summary(game_id)
    except Exception as e:
        logger.error(f"get_market_summary failed: {e}", exc_info=True)
        return {"error": str(e), "game_id": game_id}
