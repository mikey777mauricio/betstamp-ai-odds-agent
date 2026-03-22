"""
Core odds math — pure functions, no side effects.

All formulas per Betstamp spec:
- American -> Implied Probability
- Vig / Margin calculation
- No-vig fair odds
- Best available line detection
"""


def american_to_implied_probability(odds: int | float) -> float:
    """
    Convert American odds to implied probability.

    Negative odds: |odds| / (|odds| + 100)
    Positive odds: 100 / (odds + 100)

    Returns probability as a decimal (0.0 to 1.0).
    """
    odds = float(odds)
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    elif odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return 0.5  # Even money edge case


def implied_probability_to_american(prob: float) -> float:
    """
    Convert implied probability (decimal) back to American odds.

    prob > 0.5 -> negative odds
    prob < 0.5 -> positive odds
    prob == 0.5 -> +100
    """
    import math
    if math.isnan(prob) or math.isinf(prob) or prob <= 0 or prob >= 1:
        raise ValueError(f"Probability must be between 0 and 1, got {prob}")

    if prob > 0.5:
        return -(prob / (1.0 - prob)) * 100.0
    elif prob < 0.5:
        return ((1.0 - prob) / prob) * 100.0
    else:
        return 100.0


def calculate_vig(odds_a: int | float, odds_b: int | float) -> float:
    """
    Calculate the vig (margin/juice) on a two-way market.

    Sum of implied probabilities - 1.0
    Returns as a decimal (e.g., 0.0476 = 4.76%).

    Example: -110/-110 -> 52.38% + 52.38% = 104.76% -> 4.76% vig
    """
    prob_a = american_to_implied_probability(odds_a)
    prob_b = american_to_implied_probability(odds_b)
    return prob_a + prob_b - 1.0


def calculate_no_vig_probability(
    odds_a: int | float, odds_b: int | float
) -> tuple[float, float]:
    """
    Remove vig and return fair probabilities for both sides.

    Normalize implied probabilities to sum to 1.0 (100%).
    Returns (fair_prob_a, fair_prob_b).
    """
    prob_a = american_to_implied_probability(odds_a)
    prob_b = american_to_implied_probability(odds_b)
    total = prob_a + prob_b

    if total == 0:
        return (0.5, 0.5)

    return (prob_a / total, prob_b / total)


def calculate_no_vig_odds(
    odds_a: int | float, odds_b: int | float
) -> tuple[float, float]:
    """
    Calculate fair (no-vig) American odds for both sides.

    Returns (fair_american_a, fair_american_b).
    """
    fair_prob_a, fair_prob_b = calculate_no_vig_probability(odds_a, odds_b)
    return (
        implied_probability_to_american(fair_prob_a),
        implied_probability_to_american(fair_prob_b),
    )


def calculate_edge(offered_odds: int | float, fair_probability: float) -> float:
    """
    Calculate the edge (expected value) of a bet.

    edge = (1 / fair_probability) * implied_probability_of_offered - 1
    Positive edge = value bet.

    Simpler: edge = offered_implied - fair_probability
    (Negative means the offered odds imply LOWER prob than fair = value for bettor)
    """
    offered_implied = american_to_implied_probability(offered_odds)
    # Negative edge means the book is offering better than fair -> value for bettor
    return fair_probability - offered_implied


def check_arbitrage(
    odds_side_a: int | float, odds_side_b: int | float
) -> dict:
    """
    Check if a two-way market has an arbitrage opportunity.

    If the sum of implied probabilities < 1.0, there's a guaranteed profit.

    Returns dict with:
    - is_arb: bool
    - total_implied: float
    - profit_pct: float (guaranteed profit as % of stake, 0 if no arb)
    """
    prob_a = american_to_implied_probability(odds_side_a)
    prob_b = american_to_implied_probability(odds_side_b)
    total = prob_a + prob_b

    is_arb = total < 1.0
    profit_pct = ((1.0 / total) - 1.0) * 100.0 if is_arb else 0.0

    return {
        "is_arb": is_arb,
        "total_implied": total,
        "profit_pct": round(profit_pct, 4),
        "implied_a": round(prob_a, 6),
        "implied_b": round(prob_b, 6),
    }


def american_to_decimal(odds: int | float) -> float:
    """Convert American odds to decimal odds."""
    odds = float(odds)
    if odds < 0:
        return 1.0 + (100.0 / abs(odds))
    else:
        return 1.0 + (odds / 100.0)


def payout_on_100(odds: int | float) -> float:
    """
    Calculate total payout on a $100 stake.
    Useful for comparing value across books.
    """
    return 100.0 * american_to_decimal(odds)
