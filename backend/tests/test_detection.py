"""
Test detection tools against the known seeded anomalies in sample data.

Known anomalies:
- PointsBet LAL/BOS: stale (09:15, ~9hrs behind)
- BetRivers DAL/PHX: stale (11:30, ~7hrs behind)
- Caesars ATL/CHA: stale (08:00, ~10hrs behind)
- BetMGM MIL/DEN moneyline: outlier (home -195 vs consensus ~-130)
- Caesars POR/UTA total: outlier (223.5 vs consensus 217.0)
"""

import pytest
from app.tools.detection_tools import (
    _calculate_confidence,
    detect_stale_lines,
    detect_outlier_odds,
    detect_arbitrage,
    run_all_detection,
)


class TestDetectStaleLines:
    def test_finds_stale_lines(self):
        stale = detect_stale_lines()
        assert len(stale) >= 3, f"Expected at least 3 stale lines, got {len(stale)}"

    def test_finds_pointsbet_lal_bos(self):
        stale = detect_stale_lines(game_id="nba_20260320_lal_bos")
        books = [s["sportsbook"] for s in stale]
        assert "PointsBet" in books, "Should flag PointsBet LAL/BOS as stale"

    def test_finds_betrivers_dal_phx(self):
        stale = detect_stale_lines(game_id="nba_20260320_dal_phx")
        books = [s["sportsbook"] for s in stale]
        assert "BetRivers" in books, "Should flag BetRivers DAL/PHX as stale"

    def test_finds_caesars_atl_cha(self):
        stale = detect_stale_lines(game_id="nba_20260320_atl_cha")
        books = [s["sportsbook"] for s in stale]
        assert "Caesars" in books, "Should flag Caesars ATL/CHA as stale"

    def test_stale_severity(self):
        stale = detect_stale_lines()
        # Caesars ATL/CHA is 10+ hours behind -> should be high severity
        caesars_atl = [
            s for s in stale
            if s["sportsbook"] == "Caesars"
            and s["game_id"] == "nba_20260320_atl_cha"
        ]
        assert len(caesars_atl) == 1
        assert caesars_atl[0]["severity"] == "high"

    def test_stale_includes_time_details(self):
        stale = detect_stale_lines()
        for alert in stale:
            assert "minutes_behind" in alert
            assert "hours_behind" in alert
            assert alert["minutes_behind"] >= 120  # threshold
            assert "explanation" in alert

    def test_no_false_positives_fresh_game(self):
        """Games where all books updated recently should not flag."""
        # OKC/CLE game has all books within ~38 minutes of each other
        stale = detect_stale_lines(game_id="nba_20260320_cle_okc")
        assert len(stale) == 0, f"Expected no stale lines for CLE/OKC, got {len(stale)}"

    def test_custom_threshold(self):
        # With a very high threshold, should find fewer results
        stale_low = detect_stale_lines(threshold_minutes=60)
        stale_high = detect_stale_lines(threshold_minutes=600)
        assert len(stale_low) >= len(stale_high)


class TestDetectOutlierOdds:
    def test_finds_outliers(self):
        outliers = detect_outlier_odds()
        assert len(outliers) >= 1, f"Expected at least 1 outlier, got {len(outliers)}"

    def test_finds_betmgm_mil_den_moneyline(self):
        """BetMGM MIL/DEN has home ML at -195 vs consensus ~-130."""
        outliers = detect_outlier_odds(game_id="nba_20260320_den_mil")
        ml_outliers = [o for o in outliers if o["market"] == "moneyline"]
        books = [o["sportsbook"] for o in ml_outliers]
        assert "BetMGM" in books, (
            f"Should flag BetMGM MIL/DEN moneyline as outlier. "
            f"Found: {books}"
        )

    def test_finds_caesars_por_uta_total(self):
        """Caesars POR/UTA total at 223.5 vs consensus ~217."""
        outliers = detect_outlier_odds(game_id="nba_20260320_por_uta")
        total_outliers = [o for o in outliers if o["market"] == "total"]
        books = [o["sportsbook"] for o in total_outliers]
        assert "Caesars" in books, (
            f"Should flag Caesars POR/UTA total as outlier. "
            f"Found: {books}"
        )

    def test_outlier_has_math_details(self):
        outliers = detect_outlier_odds()
        for o in outliers:
            assert "z_score" in o
            assert "deviation" in o or "deviation_prob" in o
            assert "explanation" in o

    def test_z_threshold_sensitivity(self):
        # Lower threshold = more outliers
        outliers_low = detect_outlier_odds(z_threshold=1.5)
        outliers_high = detect_outlier_odds(z_threshold=3.0)
        assert len(outliers_low) >= len(outliers_high)


class TestDetectArbitrage:
    def test_returns_list(self):
        arbs = detect_arbitrage()
        assert isinstance(arbs, list)

    def test_arb_structure(self):
        arbs = detect_arbitrage()
        for arb in arbs:
            assert "type" in arb
            assert arb["type"] == "arbitrage"
            assert "market" in arb
            assert "side_a" in arb
            assert "side_b" in arb
            assert "combined_implied" in arb
            assert arb["combined_implied"] < 1.0
            assert "profit_pct" in arb
            assert arb["profit_pct"] > 0
            assert "explanation" in arb

    def test_arb_uses_different_books(self):
        """An arb must be across different sportsbooks."""
        arbs = detect_arbitrage()
        for arb in arbs:
            assert arb["side_a"]["sportsbook"] != arb["side_b"]["sportsbook"], (
                "Arbitrage should be across different books"
            )


class TestRunAllDetection:
    def test_returns_structured_summary(self):
        result = run_all_detection()
        assert "stale_lines" in result
        assert "outlier_odds" in result
        assert "arbitrage_opportunities" in result
        assert "summary" in result

    def test_summary_counts(self):
        result = run_all_detection()
        s = result["summary"]
        assert s["total_anomalies"] == s["stale_count"] + s["outlier_count"] + s["arbitrage_count"]
        assert s["stale_count"] >= 3
        assert s["outlier_count"] >= 1


class TestCalculateConfidence:
    def test_returns_valid_score_range(self):
        """Confidence score must be between 0 and 1."""
        result = _calculate_confidence(z_score=2.0, sample_size=6)
        assert 0.0 <= result["score"] <= 1.0

    def test_returns_valid_score_range_extreme_values(self):
        """Even with extreme inputs, score stays in 0-1."""
        result = _calculate_confidence(z_score=100.0, sample_size=100)
        assert 0.0 <= result["score"] <= 1.0
        result2 = _calculate_confidence(minutes_stale=10000, sample_size=50)
        assert 0.0 <= result2["score"] <= 1.0

    def test_zero_inputs_return_zero(self):
        result = _calculate_confidence()
        assert result["score"] == 0.0
        assert result["level"] == "low"

    def test_high_confidence_level(self):
        """Score > 0.75 should map to 'high'."""
        result = _calculate_confidence(minutes_stale=400, sample_size=8)
        assert result["level"] == "high"
        assert result["score"] > 0.75

    def test_medium_confidence_level(self):
        """Score between 0.4 and 0.75 should map to 'medium'."""
        result = _calculate_confidence(z_score=2.0, sample_size=7)
        assert result["level"] == "medium"
        assert 0.4 <= result["score"] <= 0.75

    def test_low_confidence_level(self):
        """Score < 0.4 should map to 'low'."""
        result = _calculate_confidence(z_score=0.5, sample_size=3)
        assert result["level"] == "low"
        assert result["score"] < 0.4

    def test_stale_line_confidence_scales_with_time(self):
        """More stale = higher confidence."""
        low = _calculate_confidence(minutes_stale=60, sample_size=6)
        high = _calculate_confidence(minutes_stale=360, sample_size=6)
        assert high["score"] > low["score"]

    def test_outlier_confidence_scales_with_z_score(self):
        """Higher z-score = higher confidence."""
        low = _calculate_confidence(z_score=1.0, sample_size=6)
        high = _calculate_confidence(z_score=3.0, sample_size=6)
        assert high["score"] > low["score"]


class TestConfidenceInAlerts:
    def test_stale_line_alerts_have_confidence(self):
        stale = detect_stale_lines()
        assert len(stale) > 0, "Need at least one stale alert to test"
        for alert in stale:
            assert "confidence" in alert
            assert "score" in alert["confidence"]
            assert "level" in alert["confidence"]
            assert 0.0 <= alert["confidence"]["score"] <= 1.0
            assert alert["confidence"]["level"] in ("high", "medium", "low")

    def test_outlier_alerts_have_confidence(self):
        outliers = detect_outlier_odds()
        assert len(outliers) > 0, "Need at least one outlier to test"
        for alert in outliers:
            assert "confidence" in alert
            assert "score" in alert["confidence"]
            assert "level" in alert["confidence"]
            assert 0.0 <= alert["confidence"]["score"] <= 1.0
            assert alert["confidence"]["level"] in ("high", "medium", "low")

    def test_arbitrage_alerts_have_confidence(self):
        arbs = detect_arbitrage()
        for opp in arbs:
            assert "confidence" in opp
            assert "score" in opp["confidence"]
            assert "level" in opp["confidence"]
            assert 0.0 <= opp["confidence"]["score"] <= 1.0
            assert opp["confidence"]["level"] in ("high", "medium", "low")
