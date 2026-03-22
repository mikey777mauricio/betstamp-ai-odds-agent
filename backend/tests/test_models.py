"""Tests for Pydantic models — validation, clamping, serialization."""

import pytest
from pydantic import ValidationError

from app.models.briefing import (
    StaleLineAlert,
    OutlierAlert,
    ArbitrageSide,
    ArbitrageOpportunity,
    ValuePlay,
    SportsbookRanking,
    MarketOverview,
    QualityMetrics,
    StructuredBriefing,
)


class TestStaleLineAlert:
    def test_valid_creation(self):
        alert = StaleLineAlert(
            game_id="game_1", home_team="LAL", away_team="BOS",
            sportsbook="DraftKings", minutes_behind=180.0, hours_behind=3.0,
            severity="high", confidence_score=0.85, confidence_level="high",
            explanation="Line is 3 hours behind market",
        )
        assert alert.confidence_score == 0.85

    def test_confidence_clamped_to_1(self):
        alert = StaleLineAlert(
            game_id="g", home_team="A", away_team="B", sportsbook="S",
            minutes_behind=10, hours_behind=0.1, severity="low",
            confidence_score=1.5, confidence_level="high", explanation="test",
        )
        assert alert.confidence_score == 1.0

    def test_confidence_clamped_to_0(self):
        alert = StaleLineAlert(
            game_id="g", home_team="A", away_team="B", sportsbook="S",
            minutes_behind=10, hours_behind=0.1, severity="low",
            confidence_score=-0.3, confidence_level="low", explanation="test",
        )
        assert alert.confidence_score == 0.0

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            StaleLineAlert(game_id="g", home_team="A")  # Missing many fields


class TestOutlierAlert:
    def test_valid_with_optional_fields(self):
        alert = OutlierAlert(
            game_id="g", home_team="A", away_team="B", sportsbook="S",
            market="moneyline", z_score=2.5, severity="high",
            confidence_score=0.8, confidence_level="high", explanation="test",
        )
        assert alert.value is None
        assert alert.odds is None

    def test_confidence_clamped(self):
        alert = OutlierAlert(
            game_id="g", home_team="A", away_team="B", sportsbook="S",
            market="ml", z_score=3.0, severity="high",
            confidence_score=2.0, confidence_level="high", explanation="t",
        )
        assert alert.confidence_score == 1.0


class TestArbitrageOpportunity:
    def test_valid_creation(self):
        arb = ArbitrageOpportunity(
            game_id="g", home_team="A", away_team="B", market="moneyline",
            side_a=ArbitrageSide(label="A ML", sportsbook="S1", odds=150, implied_probability=0.4, stake_on_1000=400),
            side_b=ArbitrageSide(label="B ML", sportsbook="S2", odds=-140, implied_probability=0.58, stake_on_1000=600),
            combined_implied=0.98, profit_pct=2.04, profit_on_1000=20.40,
            confidence_score=0.9, confidence_level="high", explanation="test",
        )
        assert arb.profit_pct == 2.04

    def test_confidence_clamped(self):
        arb = ArbitrageOpportunity(
            game_id="g", home_team="A", away_team="B", market="ml",
            side_a=ArbitrageSide(label="a", sportsbook="s", odds=100, implied_probability=0.5, stake_on_1000=500),
            side_b=ArbitrageSide(label="b", sportsbook="s", odds=100, implied_probability=0.5, stake_on_1000=500),
            combined_implied=1.0, profit_pct=0, profit_on_1000=0,
            confidence_score=5.0, confidence_level="high", explanation="t",
        )
        assert arb.confidence_score == 1.0


class TestSportsbookRanking:
    def test_score_clamped_to_100(self):
        r = SportsbookRanking(
            rank=1, sportsbook="Test", composite_score=150.0, grade="A+",
            avg_vig_pct=3.0, stale_flags=0, outlier_flags=0, games_covered=10,
        )
        assert r.composite_score == 100.0

    def test_score_clamped_to_0(self):
        r = SportsbookRanking(
            rank=1, sportsbook="Test", composite_score=-10.0, grade="F",
            avg_vig_pct=10.0, stale_flags=5, outlier_flags=5, games_covered=1,
        )
        assert r.composite_score == 0.0


class TestQualityMetrics:
    def test_valid_creation(self):
        q = QualityMetrics(
            overall_confidence=0.75, high_confidence_pct=0.6,
            total_alerts=5, high_confidence_alerts=3,
        )
        assert q.data_warnings == []

    def test_with_warnings(self):
        q = QualityMetrics(
            overall_confidence=0.5, high_confidence_pct=0.3,
            total_alerts=3, high_confidence_alerts=1,
            data_warnings=["Detection failed"],
        )
        assert len(q.data_warnings) == 1


class TestMarketOverview:
    def test_valid_creation(self):
        o = MarketOverview(
            total_games=10, total_sportsbooks=8, total_anomalies=5,
            stale_count=2, outlier_count=2, arbitrage_count=1,
        )
        assert o.total_anomalies == 5


class TestStructuredBriefingRoundTrip:
    def test_serialization_roundtrip(self):
        briefing = StructuredBriefing(
            overview=MarketOverview(
                total_games=1, total_sportsbooks=1, total_anomalies=0,
                stale_count=0, outlier_count=0, arbitrage_count=0,
            ),
            stale_lines=[], outlier_odds=[], arbitrage=[],
            value_plays=[], sportsbook_rankings=[],
            narrative="Test narrative summary.",
            quality_metrics=QualityMetrics(
                overall_confidence=0.0, high_confidence_pct=0.0,
                total_alerts=0, high_confidence_alerts=0,
            ),
            generated_at="2026-03-20T12:00:00Z",
            duration_seconds=1.5,
            tool_calls=[],
        )
        d = briefing.model_dump()
        rebuilt = StructuredBriefing(**d)
        assert rebuilt.narrative == "Test narrative summary."
        assert rebuilt.overview.total_games == 1
