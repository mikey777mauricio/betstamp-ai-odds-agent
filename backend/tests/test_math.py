"""
Test all odds math functions for correctness.

These tests verify the exact formulas from the Betstamp spec:
- American -> Implied Probability
- Vig / Margin
- No-vig fair odds
- Arbitrage detection
"""

import pytest
from app.tools.math_utils import (
    american_to_implied_probability,
    implied_probability_to_american,
    calculate_vig,
    calculate_no_vig_probability,
    calculate_no_vig_odds,
    calculate_edge,
    check_arbitrage,
    american_to_decimal,
    payout_on_100,
)


class TestAmericanToImpliedProbability:
    """Spec: Negative odds: |odds|/(|odds|+100). Positive: 100/(odds+100)."""

    def test_negative_150(self):
        # -150 -> 150/250 = 0.60
        assert american_to_implied_probability(-150) == pytest.approx(0.60, abs=1e-6)

    def test_positive_200(self):
        # +200 -> 100/300 = 0.3333...
        assert american_to_implied_probability(200) == pytest.approx(1 / 3, abs=1e-6)

    def test_negative_110(self):
        # -110 -> 110/210 = 0.52381...
        assert american_to_implied_probability(-110) == pytest.approx(
            110 / 210, abs=1e-6
        )

    def test_positive_110(self):
        # +110 -> 100/210 = 0.47619...
        assert american_to_implied_probability(110) == pytest.approx(
            100 / 210, abs=1e-6
        )

    def test_even_money_positive(self):
        # +100 -> 100/200 = 0.50
        assert american_to_implied_probability(100) == pytest.approx(0.50, abs=1e-6)

    def test_heavy_favorite(self):
        # -300 -> 300/400 = 0.75
        assert american_to_implied_probability(-300) == pytest.approx(0.75, abs=1e-6)

    def test_big_underdog(self):
        # +500 -> 100/600 = 0.1667
        assert american_to_implied_probability(500) == pytest.approx(1 / 6, abs=1e-6)

    def test_zero_odds(self):
        assert american_to_implied_probability(0) == 0.5


class TestImpliedProbabilityToAmerican:
    def test_sixty_percent(self):
        # 60% -> -150
        result = implied_probability_to_american(0.60)
        assert result == pytest.approx(-150.0, abs=0.1)

    def test_one_third(self):
        # 33.33% -> +200
        result = implied_probability_to_american(1 / 3)
        assert result == pytest.approx(200.0, abs=0.1)

    def test_fifty_percent(self):
        result = implied_probability_to_american(0.5)
        assert result == pytest.approx(100.0, abs=0.1)

    def test_roundtrip_negative(self):
        odds = -225
        prob = american_to_implied_probability(odds)
        back = implied_probability_to_american(prob)
        assert back == pytest.approx(odds, abs=0.01)

    def test_roundtrip_positive(self):
        odds = 180
        prob = american_to_implied_probability(odds)
        back = implied_probability_to_american(prob)
        assert back == pytest.approx(odds, abs=0.01)

    def test_invalid_zero(self):
        with pytest.raises(ValueError):
            implied_probability_to_american(0)

    def test_invalid_one(self):
        with pytest.raises(ValueError):
            implied_probability_to_american(1.0)


class TestCalculateVig:
    """Spec: Sum implied probs - 1. Example: -110/-110 -> 4.76% vig."""

    def test_standard_vig(self):
        # -110/-110 -> 52.38% + 52.38% = 104.76% -> 4.76% vig
        vig = calculate_vig(-110, -110)
        assert vig == pytest.approx(0.0476, abs=0.001)

    def test_no_vig(self):
        # Theoretical market with no vig: +100/+100
        # 50% + 50% = 100% -> 0% vig
        vig = calculate_vig(100, 100)
        assert vig == pytest.approx(0.0, abs=1e-6)

    def test_high_vig(self):
        # -120/-120 -> higher vig
        vig = calculate_vig(-120, -120)
        assert vig > 0.05  # > 5% vig

    def test_asymmetric_vig(self):
        # -150/+130 -> 60% + 43.48% = 103.48% -> 3.48% vig
        vig = calculate_vig(-150, 130)
        expected = (150 / 250) + (100 / 230) - 1.0
        assert vig == pytest.approx(expected, abs=1e-6)

    def test_pinnacle_low_vig(self):
        # Pinnacle typically has 2-3% vig
        # -108/-108 example
        vig = calculate_vig(-108, -108)
        assert 0.02 < vig < 0.05


class TestNoVigProbability:
    def test_standard_market(self):
        # -110/-110 -> fair 50/50
        fair_a, fair_b = calculate_no_vig_probability(-110, -110)
        assert fair_a == pytest.approx(0.5, abs=1e-6)
        assert fair_b == pytest.approx(0.5, abs=1e-6)

    def test_sums_to_one(self):
        fair_a, fair_b = calculate_no_vig_probability(-200, 170)
        assert fair_a + fair_b == pytest.approx(1.0, abs=1e-6)

    def test_favorite_underdog(self):
        fair_a, fair_b = calculate_no_vig_probability(-200, 170)
        assert fair_a > 0.5  # favorite
        assert fair_b < 0.5  # underdog


class TestNoVigOdds:
    def test_standard_market(self):
        # -110/-110 -> fair +100/+100
        fair_a, fair_b = calculate_no_vig_odds(-110, -110)
        assert fair_a == pytest.approx(100.0, abs=0.1)
        assert fair_b == pytest.approx(100.0, abs=0.1)


class TestCheckArbitrage:
    def test_no_arb_standard(self):
        # Normal market: -110/-110 -> no arb
        result = check_arbitrage(-110, -110)
        assert result["is_arb"] is False
        assert result["profit_pct"] == 0.0

    def test_arb_opportunity(self):
        # Artificial arb: +110/+110 -> 47.6% + 47.6% = 95.2% < 100%
        result = check_arbitrage(110, 110)
        assert result["is_arb"] is True
        assert result["profit_pct"] > 0

    def test_arb_math(self):
        # +100/+100 -> 50% + 50% = 100% -> NO arb (exactly breakeven)
        result = check_arbitrage(100, 100)
        assert result["is_arb"] is False

    def test_arb_profit_calculation(self):
        # If total implied = 0.95, profit = (1/0.95 - 1) * 100 = 5.26%
        result = check_arbitrage(110, 110)
        total = result["total_implied"]
        expected_profit = ((1.0 / total) - 1.0) * 100
        assert result["profit_pct"] == pytest.approx(expected_profit, abs=0.01)


class TestAmericanToDecimal:
    def test_negative_150(self):
        # -150 -> 1 + 100/150 = 1.6667
        assert american_to_decimal(-150) == pytest.approx(1.6667, abs=0.001)

    def test_positive_200(self):
        # +200 -> 1 + 200/100 = 3.0
        assert american_to_decimal(200) == pytest.approx(3.0, abs=0.001)

    def test_even_money(self):
        # +100 -> 2.0
        assert american_to_decimal(100) == pytest.approx(2.0, abs=0.001)

    def test_negative_110(self):
        # -110 -> 1 + 100/110 = 1.909...
        assert american_to_decimal(-110) == pytest.approx(1.9091, abs=0.001)


class TestPayoutOn100:
    def test_negative_150(self):
        # $100 at -150 -> $166.67 total
        assert payout_on_100(-150) == pytest.approx(166.67, abs=0.1)

    def test_positive_200(self):
        # $100 at +200 -> $300 total
        assert payout_on_100(200) == pytest.approx(300.0, abs=0.1)
