"""Strands @tool wrappers for on-demand math calculations."""

import logging
from strands import tool

from app.agent.tools.trace import _log_tool_call
from app.tools.math_utils import (
    american_to_implied_probability,
    calculate_vig,
    calculate_no_vig_odds,
    check_arbitrage,
)

logger = logging.getLogger(__name__)


@tool
def calculate_implied_probability(american_odds: int) -> dict:
    """Convert American odds to implied probability.
    Negative odds: |odds|/(|odds|+100). Positive: 100/(odds+100).

    When to use: Convert a single odds value to probability for comparison.

    Args:
        american_odds: American format odds (e.g., -150, +200)
    """
    _log_tool_call("calculate_implied_probability", {"american_odds": american_odds})
    try:
        prob = american_to_implied_probability(american_odds)
        return {
            "american_odds": american_odds,
            "implied_probability": round(prob, 6),
            "implied_probability_pct": round(prob * 100, 2),
            "formula": f"|{american_odds}|/({abs(american_odds)}+100)" if american_odds < 0
                       else f"100/({american_odds}+100)",
        }
    except Exception as e:
        logger.error(f"calculate_implied_probability failed: {e}", exc_info=True)
        return {"error": str(e), "american_odds": american_odds}


@tool
def calculate_vig_tool(odds_side_a: int, odds_side_b: int) -> dict:
    """Calculate the vig (margin) on a two-way market.
    Sum implied probabilities of both sides, subtract 100%.

    When to use: Check how much juice a sportsbook is charging on a specific market.

    Args:
        odds_side_a: American odds on side A
        odds_side_b: American odds on side B
    """
    _log_tool_call("calculate_vig", {"odds_side_a": odds_side_a, "odds_side_b": odds_side_b})
    try:
        vig = calculate_vig(odds_side_a, odds_side_b)
        prob_a = american_to_implied_probability(odds_side_a)
        prob_b = american_to_implied_probability(odds_side_b)

        return {
            "odds_a": odds_side_a,
            "odds_b": odds_side_b,
            "implied_prob_a": round(prob_a * 100, 2),
            "implied_prob_b": round(prob_b * 100, 2),
            "total_implied": round((prob_a + prob_b) * 100, 2),
            "vig_pct": round(vig * 100, 2),
            "math": (
                f"{round(prob_a * 100, 2)}% + {round(prob_b * 100, 2)}% = "
                f"{round((prob_a + prob_b) * 100, 2)}% -> "
                f"{round(vig * 100, 2)}% vig"
            ),
        }
    except Exception as e:
        logger.error(f"calculate_vig failed: {e}", exc_info=True)
        return {"error": str(e), "odds_a": odds_side_a, "odds_b": odds_side_b}


@tool
def calculate_fair_odds(odds_side_a: int, odds_side_b: int) -> dict:
    """Calculate no-vig fair odds by removing the margin and normalizing.

    When to use: Determine the true probability of each side without the book's margin.

    Args:
        odds_side_a: American odds on side A
        odds_side_b: American odds on side B
    """
    _log_tool_call("calculate_fair_odds", {"odds_side_a": odds_side_a, "odds_side_b": odds_side_b})
    try:
        prob_a = american_to_implied_probability(odds_side_a)
        prob_b = american_to_implied_probability(odds_side_b)
        total = prob_a + prob_b
        fair_prob_a = prob_a / total if total > 0 else 0.5
        fair_prob_b = prob_b / total if total > 0 else 0.5
        fair_a, fair_b = calculate_no_vig_odds(odds_side_a, odds_side_b)
        return {
            "offered_a": odds_side_a,
            "offered_b": odds_side_b,
            "fair_odds_a": round(fair_a, 1),
            "fair_odds_b": round(fair_b, 1),
            "fair_prob_a_pct": round(fair_prob_a * 100, 2),
            "fair_prob_b_pct": round(fair_prob_b * 100, 2),
            "math": (
                f"Raw implied: {round(prob_a * 100, 2)}% + {round(prob_b * 100, 2)}% = {round(total * 100, 2)}%. "
                f"Normalized: {round(fair_prob_a * 100, 2)}% / {round(fair_prob_b * 100, 2)}% "
                f"-> fair odds {round(fair_a, 1)} / {round(fair_b, 1)}"
            ),
        }
    except Exception as e:
        logger.error(f"calculate_fair_odds failed: {e}", exc_info=True)
        return {"error": str(e), "odds_a": odds_side_a, "odds_b": odds_side_b}


@tool
def check_arbitrage_tool(odds_side_a: int, odds_side_b: int) -> dict:
    """Check if two odds from different books create an arbitrage opportunity.

    When to use: Verify if a specific pair of odds creates a guaranteed-profit opportunity.

    Args:
        odds_side_a: Best odds on side A (from any book)
        odds_side_b: Best odds on side B (from any book)
    """
    _log_tool_call("check_arbitrage", {"odds_side_a": odds_side_a, "odds_side_b": odds_side_b})
    try:
        result = check_arbitrage(odds_side_a, odds_side_b)
        prob_a = american_to_implied_probability(odds_side_a)
        prob_b = american_to_implied_probability(odds_side_b)
        result["math"] = (
            f"Implied A: {round(prob_a * 100, 2)}% + Implied B: {round(prob_b * 100, 2)}% = "
            f"{round((prob_a + prob_b) * 100, 2)}%. "
            f"{'Arb exists! ' + str(result.get('profit_pct', 0)) + '% guaranteed profit' if result.get('is_arb') else 'No arb (combined > 100%)'}"
        )
        return result
    except Exception as e:
        logger.error(f"check_arbitrage failed: {e}", exc_info=True)
        return {"error": str(e), "odds_a": odds_side_a, "odds_b": odds_side_b}
