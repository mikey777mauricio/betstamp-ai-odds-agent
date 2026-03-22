"""Strands @tool wrappers for anomaly detection operations."""

import logging
from strands import tool

from app.agent.tools.trace import _log_tool_call
from app.tools.detection_tools import (
    detect_stale_lines,
    detect_outlier_odds,
    detect_arbitrage,
    run_all_detection,
)

logger = logging.getLogger(__name__)

_EMPTY_DETECTION = {
    "stale_lines": [],
    "outlier_odds": [],
    "arbitrage_opportunities": [],
    "summary": {"total_anomalies": 0, "stale_count": 0, "outlier_count": 0, "arbitrage_count": 0},
}


@tool
def run_detection(threshold_minutes: int = 120, z_threshold: float = 2.0) -> dict:
    """Run the full anomaly detection suite across all games.
    Detects stale lines, outlier odds, and arbitrage opportunities.
    Returns structured results with severity levels and explanations.

    When to use: For the daily briefing or any comprehensive scan.
    For single-game checks, use the individual detect_* tools instead.

    Args:
        threshold_minutes: Minutes behind market to flag as stale (default 120)
        z_threshold: Z-score threshold for outlier detection (default 2.0)
    """
    _log_tool_call("run_detection", {"threshold_minutes": threshold_minutes, "z_threshold": z_threshold})
    try:
        result = run_all_detection(threshold_minutes=threshold_minutes, z_threshold=z_threshold)
        if result["summary"]["total_anomalies"] == 0:
            logger.info("Detection found 0 anomalies — data may be clean or not loaded")
        return result
    except Exception as e:
        logger.error(f"run_detection failed: {e}", exc_info=True)
        return {**_EMPTY_DETECTION, "error": str(e)}


@tool
def detect_stale_lines_tool(game_id: str = "", threshold_minutes: int = 120) -> dict:
    """Detect stale lines for a specific game or all games.
    A line is stale when its last_updated is significantly older than other books.

    When to use: Check if a specific book's lines are outdated for a game.

    Args:
        game_id: Optional game ID to check (empty = all games)
        threshold_minutes: Minutes behind to flag as stale
    """
    _log_tool_call("detect_stale_lines", {"game_id": game_id, "threshold_minutes": threshold_minutes})
    try:
        gid = game_id if game_id else None
        alerts = detect_stale_lines(game_id=gid, threshold_minutes=threshold_minutes)
        return {"stale_alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.error(f"detect_stale_lines failed: {e}", exc_info=True)
        return {"error": str(e), "stale_alerts": [], "count": 0}


@tool
def detect_outlier_odds_tool(game_id: str = "", z_threshold: float = 2.0) -> dict:
    """Detect outlier odds that deviate significantly from market consensus.
    Uses robust statistical methods (median absolute deviation).

    When to use: Find mispriced lines that differ from the market consensus.

    Args:
        game_id: Optional game ID to check (empty = all games)
        z_threshold: Z-score threshold (lower = more sensitive)
    """
    _log_tool_call("detect_outlier_odds", {"game_id": game_id, "z_threshold": z_threshold})
    try:
        gid = game_id if game_id else None
        alerts = detect_outlier_odds(game_id=gid, z_threshold=z_threshold)
        return {"outlier_alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.error(f"detect_outlier_odds failed: {e}", exc_info=True)
        return {"error": str(e), "outlier_alerts": [], "count": 0}


@tool
def detect_arbitrage_tool(game_id: str = "") -> dict:
    """Detect arbitrage opportunities across sportsbooks.
    An arbitrage exists when the best odds on each side of a market
    combine to an implied probability below 100%.

    When to use: Find guaranteed-profit opportunities by betting both sides.

    Args:
        game_id: Optional game ID to check (empty = all games)
    """
    _log_tool_call("detect_arbitrage", {"game_id": game_id})
    try:
        gid = game_id if game_id else None
        arbs = detect_arbitrage(game_id=gid)
        return {"arbitrage_opportunities": arbs, "count": len(arbs)}
    except Exception as e:
        logger.error(f"detect_arbitrage failed: {e}", exc_info=True)
        return {"error": str(e), "arbitrage_opportunities": [], "count": 0}
