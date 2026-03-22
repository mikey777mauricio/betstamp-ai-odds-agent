"""Strands @tool wrappers for market analysis operations."""

import logging
from strands import tool

from app.agent.tools.trace import _log_tool_call
from app.tools.analysis_tools import (
    analyze_market_vig,
    find_best_lines,
    rank_sportsbooks,
    find_value_opportunities,
    run_full_analysis,
)

logger = logging.getLogger(__name__)


@tool
def run_analysis() -> dict:
    """Run the full market analysis suite across all games.
    Includes vig calculations, best lines, sportsbook rankings, and value opportunities.

    When to use: For the daily briefing — gives a comprehensive view.
    For single-game deep dives, use analyze_vig or find_best_lines_tool instead.
    """
    _log_tool_call("run_analysis", {})
    try:
        return run_full_analysis()
    except Exception as e:
        logger.error(f"run_analysis failed: {e}", exc_info=True)
        return {"error": str(e), "games_analyzed": 0, "value_opportunities": []}


@tool
def analyze_vig(game_id: str) -> dict:
    """Calculate the vig (juice/margin) for every sportsbook on a specific game.
    Shows spread vig, moneyline vig, total vig, and average.
    Identifies the sharpest (lowest vig) book.

    When to use: Compare sportsbook margins on a specific game.

    Args:
        game_id: The game to analyze
    """
    _log_tool_call("analyze_vig", {"game_id": game_id})
    try:
        return analyze_market_vig(game_id)
    except Exception as e:
        logger.error(f"analyze_vig failed: {e}", exc_info=True)
        return {"error": str(e), "game_id": game_id}


@tool
def find_best_lines_tool(game_id: str) -> dict:
    """Find the best available odds on each side of each market for a game.
    Compares across all sportsbooks. Calculates fair odds and edge.

    When to use: Find the best price on a specific game across all books.

    Args:
        game_id: The game to analyze
    """
    _log_tool_call("find_best_lines", {"game_id": game_id})
    try:
        return find_best_lines(game_id)
    except Exception as e:
        logger.error(f"find_best_lines failed: {e}", exc_info=True)
        return {"error": str(e), "game_id": game_id}


@tool
def rank_sportsbooks_tool() -> dict:
    """Rank all sportsbooks by quality. Scoring based on average vig (50% weight)
    and data quality/freshness (50% weight). Returns grades A+ through F.

    When to use: Compare which sportsbooks are best overall for tonight's slate.
    """
    _log_tool_call("rank_sportsbooks", {})
    try:
        rankings = rank_sportsbooks()
        return {"rankings": rankings, "count": len(rankings)}
    except Exception as e:
        logger.error(f"rank_sportsbooks failed: {e}", exc_info=True)
        return {"error": str(e), "rankings": [], "count": 0}


@tool
def find_value_opportunities_tool(min_edge_pct: float = 1.0) -> dict:
    """Find value betting opportunities across all games.
    A value bet exists when offered odds are better than fair probability.

    When to use: Find the most profitable bets across tonight's slate.

    Args:
        min_edge_pct: Minimum edge percentage to flag (default 1.0%)
    """
    _log_tool_call("find_value_opportunities", {"min_edge_pct": min_edge_pct})
    try:
        opps = find_value_opportunities(min_edge_pct=min_edge_pct)
        return {"opportunities": opps, "count": len(opps)}
    except Exception as e:
        logger.error(f"find_value_opportunities failed: {e}", exc_info=True)
        return {"error": str(e), "opportunities": [], "count": 0}
