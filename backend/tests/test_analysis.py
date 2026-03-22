"""
Test analysis tools — vig calculation, best lines, rankings, value detection.
"""

import pytest
from app.tools.analysis_tools import (
    analyze_market_vig,
    find_best_lines,
    rank_sportsbooks,
    get_market_summary,
    find_value_opportunities,
    run_full_analysis,
)


class TestAnalyzeMarketVig:
    def test_returns_vig_for_all_books(self):
        result = analyze_market_vig("nba_20260320_lal_bos")
        assert "vig_by_book" in result
        assert len(result["vig_by_book"]) == 8  # 8 sportsbooks

    def test_pinnacle_lowest_vig(self):
        """Pinnacle is known for tightest margins per the data notes."""
        result = analyze_market_vig("nba_20260320_lal_bos")
        pinnacle = next(
            b for b in result["vig_by_book"] if b["sportsbook"] == "Pinnacle"
        )
        avg_vigs = [
            b["avg_vig"] for b in result["vig_by_book"] if b["avg_vig"] is not None
        ]
        # Pinnacle should be among the lowest vig books
        assert pinnacle["avg_vig"] <= sorted(avg_vigs)[2], (
            "Pinnacle should be in the top 3 lowest vig"
        )

    def test_vig_values_reasonable(self):
        result = analyze_market_vig("nba_20260320_lal_bos")
        for book in result["vig_by_book"]:
            if book.get("spread_vig") is not None:
                # Vig should be between 0% and 15% for normal markets
                assert 0 <= book["spread_vig"] <= 15, (
                    f"{book['sportsbook']} spread vig {book['spread_vig']}% is unreasonable"
                )

    def test_identifies_sharpest_book(self):
        result = analyze_market_vig("nba_20260320_lal_bos")
        assert result["sharpest_book"] is not None
        assert result["sharpest_avg_vig"] is not None


class TestFindBestLines:
    def test_returns_all_markets(self):
        result = find_best_lines("nba_20260320_lal_bos")
        assert "best_lines" in result
        assert "spread" in result["best_lines"]
        assert "moneyline" in result["best_lines"]
        assert "total" in result["best_lines"]

    def test_best_line_is_actually_best(self):
        """The best line should have the lowest implied probability."""
        from app.data.store import odds_store
        from app.tools.math_utils import american_to_implied_probability

        result = find_best_lines("nba_20260320_lal_bos")
        best_home_ml = result["best_lines"]["moneyline"]["home_odds"]

        # Verify it's actually the best across all books
        records = odds_store.get_odds_for_game("nba_20260320_lal_bos")
        all_home_probs = [
            american_to_implied_probability(r["markets"]["moneyline"]["home_odds"])
            for r in records
        ]
        assert best_home_ml["implied_prob"] == pytest.approx(
            min(all_home_probs), abs=0.001
        )

    def test_edge_calculation_present(self):
        result = find_best_lines("nba_20260320_lal_bos")
        # Best lines should have edge calculated
        ml = result["best_lines"]["moneyline"]
        if "home_odds" in ml:
            assert "edge" in ml["home_odds"]


class TestRankSportsbooks:
    def test_returns_all_books(self):
        rankings = rank_sportsbooks()
        assert len(rankings) == 8

    def test_rankings_sorted(self):
        rankings = rank_sportsbooks()
        scores = [r["composite_score"] for r in rankings]
        assert scores == sorted(scores, reverse=True)

    def test_pinnacle_ranks_high(self):
        """Pinnacle should rank in the top 3 due to low vig."""
        rankings = rank_sportsbooks()
        pinnacle = next(r for r in rankings if r["sportsbook"] == "Pinnacle")
        assert pinnacle["rank"] <= 3, (
            f"Pinnacle ranked {pinnacle['rank']}, expected top 3"
        )

    def test_books_with_issues_rank_lower(self):
        """Books with stale/outlier flags should score lower."""
        rankings = rank_sportsbooks()
        for r in rankings:
            if r["stale_flags"] > 0 or r["outlier_flags"] > 0:
                assert r["issue_score"] < 100

    def test_ranking_has_grade(self):
        rankings = rank_sportsbooks()
        valid_grades = {"A+", "A", "B+", "B", "C", "D", "F"}
        for r in rankings:
            assert r["grade"] in valid_grades


class TestGetMarketSummary:
    def test_basic_structure(self):
        result = get_market_summary("nba_20260320_lal_bos")
        assert result["home_team"] == "Boston Celtics"
        assert result["away_team"] == "Los Angeles Lakers"
        assert result["books_reporting"] == 8

    def test_consensus_values(self):
        result = get_market_summary("nba_20260320_lal_bos")
        # Consensus spread should be around -5.5 (most books agree)
        assert result["consensus_spread"] == pytest.approx(-5.5, abs=0.5)
        # Consensus total should be around 219.5-220
        assert 218 <= result["consensus_total"] <= 221
        # Home win prob should be in reasonable range
        assert 55 <= result["consensus_home_win_prob"] <= 75

    def test_invalid_game(self):
        result = get_market_summary("nonexistent_game")
        assert "error" in result


class TestFindValueOpportunities:
    def test_returns_list(self):
        opps = find_value_opportunities()
        assert isinstance(opps, list)

    def test_opportunities_sorted_by_edge(self):
        opps = find_value_opportunities()
        if len(opps) >= 2:
            edges = [o["edge_pct"] for o in opps]
            assert edges == sorted(edges, reverse=True)

    def test_opportunity_structure(self):
        opps = find_value_opportunities(min_edge_pct=0.5)
        for opp in opps:
            assert "game_id" in opp
            assert "sportsbook" in opp
            assert "odds" in opp
            assert "edge_pct" in opp
            assert "confidence" in opp
            assert opp["edge_pct"] >= 0.5

    def test_min_edge_filter(self):
        opps_low = find_value_opportunities(min_edge_pct=0.5)
        opps_high = find_value_opportunities(min_edge_pct=3.0)
        assert len(opps_low) >= len(opps_high)


class TestRunFullAnalysis:
    def test_complete_output(self):
        result = run_full_analysis()
        assert result["games_analyzed"] == 10
        assert len(result["market_summaries"]) == 10
        assert len(result["sportsbook_rankings"]) == 8
        assert "value_opportunities" in result
        assert "value_count" in result
