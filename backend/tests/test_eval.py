"""Tests for the BriefingEvaluator."""

import pytest
from app.eval.evaluator import BriefingEvaluator


@pytest.fixture
def evaluator():
    return BriefingEvaluator()


# ── Completeness ──────────────────────────────────────────────────────────────

FULL_BRIEFING = """
## Market Overview
Today's NBA slate features 5 games across major sportsbooks.

## Anomaly Detection
We detected several stale lines and outlier odds.

## Arbitrage Opportunities
No clear arbitrage found today, but margins are thin.

## Value Opportunities
DraftKings offers value on the Lakers moneyline.

## Sportsbook Rankings
FanDuel leads with the tightest lines and best freshness.
"""

PARTIAL_BRIEFING = """
## Market Overview
Some games today.

## Arbitrage
No arbs found.
"""


class TestCompleteness:
    def test_full_briefing_scores_1(self, evaluator):
        scores = evaluator.evaluate(FULL_BRIEFING, [])
        assert scores["completeness"] == 1.0

    def test_empty_briefing_scores_0(self, evaluator):
        scores = evaluator.evaluate("", [])
        assert scores["completeness"] == 0.0

    def test_partial_briefing_scores_between(self, evaluator):
        scores = evaluator.evaluate(PARTIAL_BRIEFING, [])
        assert 0.0 < scores["completeness"] < 1.0
        # "market overview" and "arbitrage" present => 2/5 = 0.4
        assert scores["completeness"] == pytest.approx(0.4)


# ── Tool Coverage ─────────────────────────────────────────────────────────────

ALL_TOOLS_CALLS = [
    {"tool": "get_games", "input": {}},
    {"tool": "run_detection", "input": {}},
    {"tool": "run_analysis", "input": {}},
]

SOME_TOOLS_CALLS = [
    {"tool": "get_games", "input": {}},
    {"tool": "run_detection", "input": {}},
]

GRANULAR_TOOLS_CALLS = [
    {"tool": "get_odds_for_game", "input": {"game_id": "nba_123"}},
    {"tool": "detect_stale_lines", "input": {}},
    {"tool": "analyze_vig", "input": {"game_id": "nba_123"}},
]


class TestToolCoverage:
    def test_all_categories_covered(self, evaluator):
        scores = evaluator.evaluate("", ALL_TOOLS_CALLS)
        assert scores["tool_coverage"] == 1.0

    def test_no_tools_scores_0(self, evaluator):
        scores = evaluator.evaluate("", [])
        assert scores["tool_coverage"] == 0.0

    def test_some_categories_covered(self, evaluator):
        scores = evaluator.evaluate("", SOME_TOOLS_CALLS)
        # data + detection = 2/3
        assert scores["tool_coverage"] == pytest.approx(2 / 3, abs=0.01)

    def test_granular_tools_cover_categories(self, evaluator):
        """Individual tools (not just run_detection/run_analysis) should count."""
        scores = evaluator.evaluate("", GRANULAR_TOOLS_CALLS)
        assert scores["tool_coverage"] == 1.0


# ── Composite Score ───────────────────────────────────────────────────────────

class TestCompositeScore:
    def test_composite_is_weighted_average(self, evaluator):
        scores = evaluator.evaluate(FULL_BRIEFING, ALL_TOOLS_CALLS)
        expected = (
            scores["completeness"] * 0.50
            + scores["tool_coverage"] * 0.50
        )
        assert scores["composite_score"] == pytest.approx(expected, abs=0.001)

    def test_perfect_briefing_composite_near_1(self, evaluator):
        """A briefing with all sections and all tools."""
        scores = evaluator.evaluate(FULL_BRIEFING, ALL_TOOLS_CALLS)
        assert scores["composite_score"] >= 0.8

    def test_empty_everything_scores_0(self, evaluator):
        scores = evaluator.evaluate("", [])
        assert scores["composite_score"] == 0.0


# ── Structured Data Evaluation ───────────────────────────────────────────────

STRUCTURED_BRIEFING_DATA = {
    "overview": {"total_games": 10, "total_sportsbooks": 8, "total_anomalies": 5},
    "stale_lines": [
        {"sportsbook": "PointsBet", "game_id": "nba_20260320_lal_bos"},
        {"sportsbook": "BetRivers", "game_id": "nba_20260320_dal_phx"},
        {"sportsbook": "Caesars", "game_id": "nba_20260320_atl_cha"},
    ],
    "outlier_odds": [
        {"sportsbook": "BetMGM", "game_id": "nba_20260320_mil_den"},
        {"sportsbook": "Caesars", "game_id": "nba_20260320_por_uta"},
    ],
    "arbitrage": [{"game_id": "arb_1"}],
    "value_plays": [{"game_id": "val_1"}, {"game_id": "val_2"}],
    "sportsbook_rankings": [{"rank": 1}, {"rank": 2}],
    "narrative": "Test narrative about tonight's games.",
    "quality_metrics": {"overall_confidence": 0.75},
}


class TestStructuredEvaluation:
    def test_structured_completeness_full(self, evaluator):
        scores = evaluator.evaluate("test", [], structured_data=STRUCTURED_BRIEFING_DATA)
        assert "structured_completeness" in scores
        assert scores["structured_completeness"] == 1.0  # All 8 sections populated

    def test_structured_completeness_partial(self, evaluator):
        partial = {"overview": {}, "stale_lines": [{"x": 1}], "narrative": "hi"}
        scores = evaluator.evaluate("test", [], structured_data=partial)
        assert 0 < scores["structured_completeness"] < 1.0

    def test_structured_composite_includes_structured_score(self, evaluator):
        scores = evaluator.evaluate("", ALL_TOOLS_CALLS, structured_data=STRUCTURED_BRIEFING_DATA)
        assert "structured_completeness" in scores
        assert scores["composite_score"] > 0


# ── Consistency ──────────────────────────────────────────────────────────────

CONSISTENT_NARRATIVE = """
Tonight's analysis flagged 3 stale lines and 2 outlier odds across 8 sportsbooks.
PointsBet and BetRivers have the most stale data. BetMGM was flagged as an outlier.
We found 1 arbitrage opportunity with an 8.12% profit margin.
Caesars has a 4.52% average vig, while FanDuel leads at 3.21%.
"""

INCONSISTENT_NARRATIVE = """
No arbitrage opportunities were found tonight. There are 5 stale lines across books.
WynnBet was flagged for outlier pricing on the Lakers game.
The best vig at 1.50% was at Barstool.
"""

STRUCTURED_DATA_FOR_CONSISTENCY = {
    "overview": {"total_games": 10, "total_sportsbooks": 8, "total_anomalies": 5},
    "stale_lines": [
        {"sportsbook": "PointsBet", "game_id": "nba_20260320_lal_bos"},
        {"sportsbook": "BetRivers", "game_id": "nba_20260320_dal_phx"},
        {"sportsbook": "Caesars", "game_id": "nba_20260320_atl_cha"},
    ],
    "outlier_odds": [
        {"sportsbook": "BetMGM", "game_id": "nba_20260320_mil_den"},
        {"sportsbook": "Caesars", "game_id": "nba_20260320_por_uta"},
    ],
    "arbitrage": [{"game_id": "arb_1", "profit_pct": 8.12}],
    "value_plays": [{"game_id": "val_1", "edge_pct": 3.5}],
    "sportsbook_rankings": [
        {"rank": 1, "sportsbook": "FanDuel", "avg_vig_pct": 3.21},
        {"rank": 2, "sportsbook": "Caesars", "avg_vig_pct": 4.52},
    ],
    "narrative": "Test narrative.",
    "quality_metrics": {"overall_confidence": 0.75},
}


class TestConsistency:
    def test_consistent_narrative_scores_high(self, evaluator):
        scores = evaluator.evaluate(
            CONSISTENT_NARRATIVE, [], structured_data=STRUCTURED_DATA_FOR_CONSISTENCY
        )
        assert "consistency" in scores
        assert scores["consistency"] >= 0.7

    def test_inconsistent_narrative_scores_low(self, evaluator):
        scores = evaluator.evaluate(
            INCONSISTENT_NARRATIVE, [], structured_data=STRUCTURED_DATA_FOR_CONSISTENCY
        )
        assert scores["consistency"] < 0.6

    def test_empty_narrative_scores_zero(self, evaluator):
        scores = evaluator.evaluate(
            "", [], structured_data=STRUCTURED_DATA_FOR_CONSISTENCY
        )
        assert scores["consistency"] == 0.0

    def test_no_structured_data_no_consistency(self, evaluator):
        """Without structured data, consistency is not computed."""
        scores = evaluator.evaluate(CONSISTENT_NARRATIVE, [])
        assert "consistency" not in scores

    def test_presence_contradiction_penalized(self, evaluator):
        """Narrative claims 'no arbitrage' but data has an arb."""
        text = "No arbitrage opportunities were found tonight."
        scores = evaluator.evaluate(
            text, [], structured_data=STRUCTURED_DATA_FOR_CONSISTENCY
        )
        assert scores["consistency"] < 0.8

    def test_correct_counts_rewarded(self, evaluator):
        """Narrative with exact matching counts should score well on consistency."""
        text = "Found 3 stale lines and 2 outlier odds tonight. 1 arbitrage detected."
        scores = evaluator.evaluate(
            text, [], structured_data=STRUCTURED_DATA_FOR_CONSISTENCY
        )
        assert scores["consistency"] >= 0.6

    def test_wrong_counts_penalized(self, evaluator):
        """Narrative with wrong counts should score lower."""
        text = "Found 7 stale lines and 0 outlier odds tonight."
        scores = evaluator.evaluate(
            text, [], structured_data=STRUCTURED_DATA_FOR_CONSISTENCY
        )
        assert scores["consistency"] < 0.7

    def test_consistency_in_composite(self, evaluator):
        """Consistency should be factored into composite score."""
        scores = evaluator.evaluate(
            CONSISTENT_NARRATIVE, ALL_TOOLS_CALLS,
            structured_data=STRUCTURED_DATA_FOR_CONSISTENCY,
        )
        expected = (
            scores["completeness"] * 0.20
            + scores["tool_coverage"] * 0.20
            + scores["structured_completeness"] * 0.30
            + scores["consistency"] * 0.30
        )
        assert scores["composite_score"] == pytest.approx(expected, abs=0.001)
