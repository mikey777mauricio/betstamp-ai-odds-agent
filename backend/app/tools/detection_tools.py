"""
Stage 1: DETECT — Anomaly detection tools.

Pure Python, deterministic. These are exposed as agent tools via @tool decorator
but the logic lives here for testability.
"""

from datetime import datetime, timezone
from statistics import median, mean
from app.data.store import odds_store
from app.tools.math_utils import (
    american_to_implied_probability,
    check_arbitrage,
)


def _calculate_confidence(
    z_score: float = 0,
    sample_size: int = 0,
    deviation: float = 0,
    minutes_stale: float = 0,
) -> dict:
    """
    Calculate confidence in a detection finding.

    Factors:
    - Z-score magnitude: higher = more confident (for outliers)
    - Sample size: more books = more confident
    - Deviation magnitude: larger = more confident
    - Minutes stale: more stale = more confident (for stale lines)
    """
    raw = 0.0

    if minutes_stale > 0:
        # Stale lines: 6 hours (360 min) = max confidence, scaled by sample size
        time_factor = min(minutes_stale / 360.0, 1.0)
        size_factor = min(sample_size / 6.0, 1.0) if sample_size > 0 else 0.5
        raw = time_factor * size_factor
    elif z_score > 0:
        # Outliers: z_score of 3 = max confidence, scaled by sample size
        z_factor = min(z_score / 3.0, 1.0)
        size_factor = min(sample_size / 8.0, 1.0) if sample_size > 0 else 0.5
        raw = z_factor * size_factor
    elif deviation > 0:
        # Arbitrage: 5% profit = max confidence, scaled by sample size
        profit_factor = min(deviation / 5.0, 1.0)
        size_factor = min(sample_size / 6.0, 1.0) if sample_size > 0 else 0.5
        raw = profit_factor * size_factor

    score = max(0.0, min(1.0, raw))

    if score > 0.75:
        level = "high"
    elif score >= 0.4:
        level = "medium"
    else:
        level = "low"

    return {"score": round(score, 4), "level": level}


def detect_stale_lines(
    game_id: str | None = None, threshold_minutes: int = 120
) -> list[dict]:
    """
    Detect stale lines where last_updated is significantly older than peers.

    For each game, find the most recent update time across all books.
    Flag any book whose last_updated is more than threshold_minutes behind.

    Returns list of stale line alerts with details.
    """
    games = [game_id] if game_id else [g["game_id"] for g in odds_store.get_games()]
    alerts = []

    for gid in games:
        records = odds_store.get_odds_for_game(gid)
        if not records:
            continue

        timestamps = []
        for r in records:
            ts = datetime.fromisoformat(r["last_updated"].replace("Z", "+00:00"))
            timestamps.append((r["sportsbook"], ts, r))

        most_recent = max(t[1] for t in timestamps)

        for sportsbook, ts, record in timestamps:
            delta_minutes = (most_recent - ts).total_seconds() / 60.0
            if delta_minutes >= threshold_minutes:
                alerts.append({
                    "type": "stale_line",
                    "severity": "high" if delta_minutes > 360 else "medium",
                    "game_id": gid,
                    "sportsbook": sportsbook,
                    "home_team": record["home_team"],
                    "away_team": record["away_team"],
                    "last_updated": record["last_updated"],
                    "most_recent_update": most_recent.isoformat(),
                    "minutes_behind": round(delta_minutes, 1),
                    "hours_behind": round(delta_minutes / 60.0, 1),
                    "explanation": (
                        f"{sportsbook} data for {record['away_team']} @ "
                        f"{record['home_team']} is {round(delta_minutes / 60.0, 1)} "
                        f"hours behind the freshest line. Odds may not reflect "
                        f"current market conditions."
                    ),
                    "confidence": _calculate_confidence(minutes_stale=delta_minutes, sample_size=len(timestamps)),
                })

    return sorted(alerts, key=lambda x: x["minutes_behind"], reverse=True)


def detect_outlier_odds(
    game_id: str | None = None, z_threshold: float = 2.0
) -> list[dict]:
    """
    Detect outlier odds that deviate significantly from market consensus.

    Uses median absolute deviation (MAD) for robust outlier detection.
    Checks spreads (line value), moneylines (implied prob), and totals (line value).

    Returns list of outlier alerts.
    """
    games = [game_id] if game_id else [g["game_id"] for g in odds_store.get_games()]
    alerts = []

    for gid in games:
        records = odds_store.get_odds_for_game(gid)
        if len(records) < 3:
            continue

        # Check spread lines
        _check_spread_outliers(gid, records, z_threshold, alerts)
        # Check moneyline implied probabilities
        _check_moneyline_outliers(gid, records, z_threshold, alerts)
        # Check total lines
        _check_total_outliers(gid, records, z_threshold, alerts)

    return alerts


def _mad(values: list[float]) -> float:
    """Median Absolute Deviation."""
    med = median(values)
    return median([abs(v - med) for v in values])


def _check_spread_outliers(
    game_id: str, records: list[dict], z_threshold: float, alerts: list
):
    """Check for outlier spread lines."""
    lines = []
    for r in records:
        spread = r.get("markets", {}).get("spread", {})
        if spread and "home_line" in spread:
            lines.append((r["sportsbook"], spread["home_line"], r))

    if len(lines) < 3:
        return

    values = [l[1] for l in lines]
    med = median(values)
    mad_val = _mad(values)

    if mad_val == 0:
        mad_val = 0.5  # minimum sensitivity for spread lines

    for sportsbook, line, record in lines:
        deviation = abs(line - med)
        z_score = deviation / mad_val if mad_val > 0 else 0

        if z_score >= z_threshold and deviation >= 1.0:
            alerts.append({
                "type": "outlier_spread",
                "severity": "high" if deviation >= 1.5 else "medium",
                "game_id": game_id,
                "sportsbook": sportsbook,
                "home_team": record["home_team"],
                "away_team": record["away_team"],
                "market": "spread",
                "value": line,
                "consensus_median": med,
                "deviation": round(deviation, 1),
                "z_score": round(z_score, 2),
                "explanation": (
                    f"{sportsbook} has {record['home_team']} spread at {line} "
                    f"vs market median {med}. Off by {round(deviation, 1)} points."
                ),
                "confidence": _calculate_confidence(z_score=z_score, sample_size=len(values), deviation=deviation),
            })


def _check_moneyline_outliers(
    game_id: str, records: list[dict], z_threshold: float, alerts: list
):
    """Check for outlier moneylines using implied probability."""
    home_probs = []
    for r in records:
        ml = r.get("markets", {}).get("moneyline", {})
        if ml and "home_odds" in ml:
            prob = american_to_implied_probability(ml["home_odds"])
            home_probs.append((r["sportsbook"], ml["home_odds"], prob, r))

    if len(home_probs) < 3:
        return

    prob_values = [p[2] for p in home_probs]
    med_prob = median(prob_values)
    mad_val = _mad(prob_values)

    if mad_val == 0:
        mad_val = 0.01  # minimum sensitivity

    for sportsbook, odds, prob, record in home_probs:
        deviation = abs(prob - med_prob)
        z_score = deviation / mad_val if mad_val > 0 else 0

        if z_score >= z_threshold and deviation >= 0.03:
            alerts.append({
                "type": "outlier_moneyline",
                "severity": "high" if deviation >= 0.05 else "medium",
                "game_id": game_id,
                "sportsbook": sportsbook,
                "home_team": record["home_team"],
                "away_team": record["away_team"],
                "market": "moneyline",
                "odds": odds,
                "implied_probability": round(prob, 4),
                "consensus_median_prob": round(med_prob, 4),
                "deviation_prob": round(deviation, 4),
                "z_score": round(z_score, 2),
                "explanation": (
                    f"{sportsbook} moneyline for {record['home_team']} ({odds}) "
                    f"implies {round(prob * 100, 1)}% vs consensus "
                    f"{round(med_prob * 100, 1)}%. "
                    f"Deviation of {round(deviation * 100, 1)} percentage points."
                ),
                "confidence": _calculate_confidence(z_score=z_score, sample_size=len(prob_values), deviation=deviation),
            })


def _check_total_outliers(
    game_id: str, records: list[dict], z_threshold: float, alerts: list
):
    """Check for outlier total lines."""
    lines = []
    for r in records:
        total = r.get("markets", {}).get("total", {})
        if total and "line" in total:
            lines.append((r["sportsbook"], total["line"], r))

    if len(lines) < 3:
        return

    values = [l[1] for l in lines]
    med = median(values)
    mad_val = _mad(values)

    if mad_val == 0:
        mad_val = 0.5  # minimum sensitivity for total lines

    for sportsbook, line, record in lines:
        deviation = abs(line - med)
        z_score = deviation / mad_val if mad_val > 0 else 0

        if z_score >= z_threshold and deviation >= 1.5:
            alerts.append({
                "type": "outlier_total",
                "severity": "high" if deviation >= 3.0 else "medium",
                "game_id": game_id,
                "sportsbook": sportsbook,
                "home_team": record["home_team"],
                "away_team": record["away_team"],
                "market": "total",
                "value": line,
                "consensus_median": med,
                "deviation": round(deviation, 1),
                "z_score": round(z_score, 2),
                "explanation": (
                    f"{sportsbook} total for {record['away_team']} @ "
                    f"{record['home_team']} is {line} vs market median {med}. "
                    f"Off by {round(deviation, 1)} points."
                ),
                "confidence": _calculate_confidence(z_score=z_score, sample_size=len(values), deviation=deviation),
            })


def detect_arbitrage(game_id: str | None = None) -> list[dict]:
    """
    Detect arbitrage opportunities across sportsbooks.

    For each game and each 2-way market (spread, moneyline, total),
    find the best odds on each side across all books.
    If combined implied probability < 100%, it's an arb.

    Returns list of arbitrage opportunities with exact math.
    """
    games = [game_id] if game_id else [g["game_id"] for g in odds_store.get_games()]
    opportunities = []

    for gid in games:
        records = odds_store.get_odds_for_game(gid)
        if len(records) < 2:
            continue

        game_info = {
            "home_team": records[0]["home_team"],
            "away_team": records[0]["away_team"],
        }

        # Check each market type
        for market_type in ["spread", "moneyline", "total"]:
            arb = _check_market_arbitrage(gid, records, market_type, game_info)
            if arb:
                opportunities.append(arb)

    return opportunities


def _check_market_arbitrage(
    game_id: str, records: list[dict], market_type: str, game_info: dict
) -> dict | None:
    """Check a specific market for arbitrage across books."""

    home = game_info.get("home_team", "Home")
    away = game_info.get("away_team", "Away")

    if market_type == "spread":
        side_a_key, side_b_key = "home_odds", "away_odds"
        side_a_label, side_b_label = f"{home} spread", f"{away} spread"
    elif market_type == "moneyline":
        side_a_key, side_b_key = "home_odds", "away_odds"
        side_a_label, side_b_label = f"{home} ML", f"{away} ML"
    elif market_type == "total":
        side_a_key, side_b_key = "over_odds", "under_odds"
        side_a_label, side_b_label = "Over", "Under"
    else:
        return None

    # Collect best odds on each side (highest payout = lowest implied prob)
    best_a = None  # (odds, sportsbook, implied_prob)
    best_b = None

    for r in records:
        market = r.get("markets", {}).get(market_type, {})
        if not market:
            continue

        odds_a = market.get(side_a_key)
        odds_b = market.get(side_b_key)

        if odds_a is not None:
            prob_a = american_to_implied_probability(odds_a)
            if best_a is None or prob_a < best_a[2]:
                best_a = (odds_a, r["sportsbook"], prob_a)

        if odds_b is not None:
            prob_b = american_to_implied_probability(odds_b)
            if best_b is None or prob_b < best_b[2]:
                best_b = (odds_b, r["sportsbook"], prob_b)

    if best_a is None or best_b is None:
        return None

    arb_check = check_arbitrage(best_a[0], best_b[0])

    if arb_check["is_arb"]:
        return {
            "type": "arbitrage",
            "severity": "critical",
            "game_id": game_id,
            "home_team": game_info["home_team"],
            "away_team": game_info["away_team"],
            "market": market_type,
            "side_a": {
                "label": side_a_label,
                "sportsbook": best_a[1],
                "odds": best_a[0],
                "implied_probability": round(best_a[2], 6),
            },
            "side_b": {
                "label": side_b_label,
                "sportsbook": best_b[1],
                "odds": best_b[0],
                "implied_probability": round(best_b[2], 6),
            },
            "combined_implied": round(arb_check["total_implied"], 6),
            "profit_pct": arb_check["profit_pct"],
            "explanation": (
                f"ARBITRAGE: {market_type} on {game_info['away_team']} @ "
                f"{game_info['home_team']}. "
                f"Bet {side_a_label} at {best_a[1]} ({best_a[0]}) + "
                f"{side_b_label} at {best_b[1]} ({best_b[0]}). "
                f"Combined implied: {round(arb_check['total_implied'] * 100, 2)}%. "
                f"Guaranteed profit: {arb_check['profit_pct']}% of total stake."
            ),
            "confidence": _calculate_confidence(deviation=arb_check["profit_pct"], sample_size=len(records)),
        }

    return None


def run_all_detection(threshold_minutes: int = 120, z_threshold: float = 2.0) -> dict:
    """
    Run the full detection suite across all games.
    Returns a structured summary of all anomalies found.
    """
    stale = detect_stale_lines(threshold_minutes=threshold_minutes)
    outliers = detect_outlier_odds(z_threshold=z_threshold)
    arbs = detect_arbitrage()

    return {
        "stale_lines": stale,
        "outlier_odds": outliers,
        "arbitrage_opportunities": arbs,
        "summary": {
            "total_anomalies": len(stale) + len(outliers) + len(arbs),
            "stale_count": len(stale),
            "outlier_count": len(outliers),
            "arbitrage_count": len(arbs),
            "high_severity": len(
                [a for a in stale + outliers if a.get("severity") == "high"]
            )
            + len(arbs),  # all arbs are critical
        },
    }
