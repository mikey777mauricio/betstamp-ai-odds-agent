"""
Stage 2: ANALYZE — Market analysis tools.

Deterministic calculations for vig, best lines, fair odds,
value opportunities, and sportsbook quality rankings.
"""

from statistics import median, mean
from app.data.store import odds_store
from app.tools.math_utils import (
    american_to_implied_probability,
    calculate_vig,
    calculate_no_vig_probability,
    calculate_no_vig_odds,
    calculate_edge,
    american_to_decimal,
    payout_on_100,
)


def analyze_market_vig(game_id: str) -> dict:
    """
    Calculate vig for every sportsbook on every market for a game.

    Returns per-book vig and identifies the sharpest (lowest vig) book.
    """
    records = odds_store.get_odds_for_game(game_id)
    if not records:
        return {"error": f"No data for game {game_id}"}

    results = []
    for r in records:
        markets = r.get("markets", {})
        book_vigs = {"sportsbook": r["sportsbook"]}

        # Spread vig
        spread = markets.get("spread", {})
        if spread and "home_odds" in spread and "away_odds" in spread:
            vig = calculate_vig(spread["home_odds"], spread["away_odds"])
            book_vigs["spread_vig"] = round(vig * 100, 2)

        # Moneyline vig
        ml = markets.get("moneyline", {})
        if ml and "home_odds" in ml and "away_odds" in ml:
            vig = calculate_vig(ml["home_odds"], ml["away_odds"])
            book_vigs["moneyline_vig"] = round(vig * 100, 2)

        # Total vig
        total = markets.get("total", {})
        if total and "over_odds" in total and "under_odds" in total:
            vig = calculate_vig(total["over_odds"], total["under_odds"])
            book_vigs["total_vig"] = round(vig * 100, 2)

        # Average vig across available markets
        vigs = [
            v for k, v in book_vigs.items()
            if k.endswith("_vig") and isinstance(v, (int, float))
        ]
        book_vigs["avg_vig"] = round(mean(vigs), 2) if vigs else None

        results.append(book_vigs)

    # Sort by avg vig (lowest = best)
    results.sort(key=lambda x: x.get("avg_vig") or 99)

    return {
        "game_id": game_id,
        "home_team": records[0]["home_team"],
        "away_team": records[0]["away_team"],
        "vig_by_book": results,
        "sharpest_book": results[0]["sportsbook"] if results else None,
        "sharpest_avg_vig": results[0].get("avg_vig") if results else None,
    }


def find_best_lines(game_id: str) -> dict:
    """
    Find the best available odds on each side of each market across all books.

    "Best" = highest payout for the bettor (lowest implied probability).
    Also calculates fair odds and edge for each opportunity.
    """
    records = odds_store.get_odds_for_game(game_id)
    if not records:
        return {"error": f"No data for game {game_id}"}

    game_info = {
        "game_id": game_id,
        "home_team": records[0]["home_team"],
        "away_team": records[0]["away_team"],
    }

    best_lines = {}

    for market_type, sides in [
        ("spread", [("home_odds", "away_odds", "home_line")]),
        ("moneyline", [("home_odds", "away_odds", None)]),
        ("total", [("over_odds", "under_odds", "line")]),
    ]:
        market_best = {}

        for side_a_key, side_b_key, line_key in sides:
            # Collect all odds for this market
            side_a_entries = []
            side_b_entries = []

            for r in records:
                market = r.get("markets", {}).get(market_type, {})
                if not market:
                    continue

                if side_a_key in market:
                    side_a_entries.append({
                        "sportsbook": r["sportsbook"],
                        "odds": market[side_a_key],
                        "implied_prob": round(
                            american_to_implied_probability(market[side_a_key]), 4
                        ),
                        "payout_on_100": round(payout_on_100(market[side_a_key]), 2),
                        "line": market.get(line_key if line_key else "home_line"),
                    })

                if side_b_key in market:
                    side_b_entries.append({
                        "sportsbook": r["sportsbook"],
                        "odds": market[side_b_key],
                        "implied_prob": round(
                            american_to_implied_probability(market[side_b_key]), 4
                        ),
                        "payout_on_100": round(payout_on_100(market[side_b_key]), 2),
                        "line": market.get(
                            "away_line" if line_key == "home_line" else line_key
                        ),
                    })

            # Best = lowest implied prob (highest payout)
            if side_a_entries:
                best_a = min(side_a_entries, key=lambda x: x["implied_prob"])
                market_best[side_a_key] = best_a

            if side_b_entries:
                best_b = min(side_b_entries, key=lambda x: x["implied_prob"])
                market_best[side_b_key] = best_b

            # Calculate fair odds using Pinnacle as reference (if available)
            # or the consensus median
            if side_a_entries and side_b_entries:
                # Use median implied probs as fair
                med_a = median([e["implied_prob"] for e in side_a_entries])
                med_b = median([e["implied_prob"] for e in side_b_entries])
                total_prob = med_a + med_b
                if total_prob > 0:
                    fair_a = med_a / total_prob
                    fair_b = med_b / total_prob
                    market_best["fair_probability_a"] = round(fair_a, 4)
                    market_best["fair_probability_b"] = round(fair_b, 4)

                    # Edge on best lines
                    if side_a_key in market_best:
                        edge_a = fair_a - market_best[side_a_key]["implied_prob"]
                        market_best[side_a_key]["edge"] = round(edge_a * 100, 2)

                    if side_b_key in market_best:
                        edge_b = fair_b - market_best[side_b_key]["implied_prob"]
                        market_best[side_b_key]["edge"] = round(edge_b * 100, 2)

        best_lines[market_type] = market_best

    return {**game_info, "best_lines": best_lines}


def rank_sportsbooks() -> list[dict]:
    """
    Rank all sportsbooks by quality across all games.

    Scoring criteria:
    1. Average vig (lower = better) — 40% weight
    2. Line freshness (more recent = better) — 30% weight
    3. Number of outlier flags (fewer = better) — 30% weight
    """
    from app.tools.detection_tools import detect_stale_lines, detect_outlier_odds
    from datetime import datetime

    books = odds_store.get_sportsbooks()
    games = odds_store.get_games()

    # Collect metrics per book
    book_metrics = {}
    for book in books:
        book_metrics[book] = {
            "sportsbook": book,
            "vigs": [],
            "update_deltas": [],  # minutes behind freshest per game
            "outlier_count": 0,
            "stale_count": 0,
            "games_covered": 0,
        }

    # Calculate vigs per book per game
    for game in games:
        records = odds_store.get_odds_for_game(game["game_id"])
        for r in records:
            book = r["sportsbook"]
            markets = r.get("markets", {})

            # Spread vig
            spread = markets.get("spread", {})
            if spread and "home_odds" in spread and "away_odds" in spread:
                vig = calculate_vig(spread["home_odds"], spread["away_odds"])
                book_metrics[book]["vigs"].append(vig)

            # ML vig
            ml = markets.get("moneyline", {})
            if ml and "home_odds" in ml and "away_odds" in ml:
                vig = calculate_vig(ml["home_odds"], ml["away_odds"])
                book_metrics[book]["vigs"].append(vig)

            # Total vig
            total = markets.get("total", {})
            if total and "over_odds" in total and "under_odds" in total:
                vig = calculate_vig(total["over_odds"], total["under_odds"])
                book_metrics[book]["vigs"].append(vig)

            book_metrics[book]["games_covered"] += 1

    # Count stale/outlier flags per book
    stale_alerts = detect_stale_lines()
    outlier_alerts = detect_outlier_odds()

    for alert in stale_alerts:
        book = alert["sportsbook"]
        if book in book_metrics:
            book_metrics[book]["stale_count"] += 1

    for alert in outlier_alerts:
        book = alert["sportsbook"]
        if book in book_metrics:
            book_metrics[book]["outlier_count"] += 1

    # Score each book
    rankings = []
    for book, metrics in book_metrics.items():
        avg_vig = mean(metrics["vigs"]) * 100 if metrics["vigs"] else 10.0
        issue_count = metrics["stale_count"] + metrics["outlier_count"]

        # Normalize scores (0-100, higher = better)
        # Vig score: 5% vig = 50, 3% = 70, 7% = 30 (inverted, lower vig = better)
        vig_score = max(0, min(100, 100 - (avg_vig - 2) * 20))

        # Issue score: 0 issues = 100, each issue -20
        issue_score = max(0, 100 - issue_count * 25)

        # Composite
        composite = round(vig_score * 0.5 + issue_score * 0.5, 1)

        rankings.append({
            "sportsbook": book,
            "composite_score": composite,
            "avg_vig_pct": round(avg_vig, 2),
            "vig_score": round(vig_score, 1),
            "issue_score": round(issue_score, 1),
            "stale_flags": metrics["stale_count"],
            "outlier_flags": metrics["outlier_count"],
            "games_covered": metrics["games_covered"],
            "grade": _score_to_grade(composite),
        })

    rankings.sort(key=lambda x: x["composite_score"], reverse=True)

    # Add rank
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    return rankings


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B+"
    elif score >= 60:
        return "B"
    elif score >= 50:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "F"


def get_market_summary(game_id: str) -> dict:
    """
    Get a comprehensive market summary for a single game.
    Combines consensus lines, vig analysis, and best available odds.
    """
    records = odds_store.get_odds_for_game(game_id)
    if not records:
        return {"error": f"No data for game {game_id}"}

    game_info = {
        "game_id": game_id,
        "home_team": records[0]["home_team"],
        "away_team": records[0]["away_team"],
        "commence_time": records[0]["commence_time"],
        "books_reporting": len(records),
    }

    # Consensus spread
    spreads = [
        r["markets"]["spread"]["home_line"]
        for r in records
        if r.get("markets", {}).get("spread", {}).get("home_line") is not None
    ]
    if spreads:
        game_info["consensus_spread"] = median(spreads)
        game_info["spread_range"] = [min(spreads), max(spreads)]

    # Consensus total
    totals = [
        r["markets"]["total"]["line"]
        for r in records
        if r.get("markets", {}).get("total", {}).get("line") is not None
    ]
    if totals:
        game_info["consensus_total"] = median(totals)
        game_info["total_range"] = [min(totals), max(totals)]

    # Consensus moneyline (using implied probability)
    home_probs = [
        american_to_implied_probability(r["markets"]["moneyline"]["home_odds"])
        for r in records
        if r.get("markets", {}).get("moneyline", {}).get("home_odds") is not None
    ]
    if home_probs:
        med_home = median(home_probs)
        game_info["consensus_home_win_prob"] = round(med_home * 100, 1)
        game_info["consensus_away_win_prob"] = round((1 - med_home) * 100, 1)

    return game_info


def find_value_opportunities(min_edge_pct: float = 1.0) -> list[dict]:
    """
    Scan all games for value betting opportunities.

    A value bet exists when a sportsbook offers odds that imply a lower
    probability than the fair (no-vig) consensus probability.

    min_edge_pct: minimum edge required to flag as value (default 1%)
    """
    games = odds_store.get_games()
    opportunities = []

    for game in games:
        best = find_best_lines(game["game_id"])
        if "error" in best:
            continue

        for market_type, market_data in best.get("best_lines", {}).items():
            for key in market_data:
                entry = market_data[key]
                if isinstance(entry, dict) and "edge" in entry:
                    if entry["edge"] >= min_edge_pct:
                        opportunities.append({
                            "game_id": game["game_id"],
                            "home_team": game["home_team"],
                            "away_team": game["away_team"],
                            "market": market_type,
                            "side": key,
                            "sportsbook": entry["sportsbook"],
                            "odds": entry["odds"],
                            "edge_pct": entry["edge"],
                            "implied_prob": entry["implied_prob"],
                            "payout_on_100": entry["payout_on_100"],
                            "confidence": _edge_to_confidence(entry["edge"]),
                        })

    opportunities.sort(key=lambda x: x["edge_pct"], reverse=True)
    return opportunities


def _edge_to_confidence(edge: float) -> str:
    """Convert edge percentage to confidence label."""
    if edge >= 3.0:
        return "high"
    elif edge >= 1.5:
        return "medium"
    else:
        return "low"


def run_full_analysis() -> dict:
    """
    Run the complete analysis suite across all games.
    Returns structured results for the briefing stage.
    """
    games = odds_store.get_games()

    market_summaries = []
    for game in games:
        summary = get_market_summary(game["game_id"])
        vig_analysis = analyze_market_vig(game["game_id"])
        best = find_best_lines(game["game_id"])

        market_summaries.append({
            "summary": summary,
            "vig": vig_analysis,
            "best_lines": best.get("best_lines", {}),
        })

    rankings = rank_sportsbooks()
    value_opps = find_value_opportunities()

    return {
        "games_analyzed": len(games),
        "market_summaries": market_summaries,
        "sportsbook_rankings": rankings,
        "value_opportunities": value_opps,
        "value_count": len(value_opps),
    }
