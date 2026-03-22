"""
Briefing Evaluator — scores agent-generated briefings on quality metrics.

Supports both legacy markdown briefings and structured briefings (Pydantic).

Metrics:
1. completeness   (0-1): Required sections present in the briefing text
2. tool_coverage  (0-1): Required tool categories called during generation
3. structured_completeness (0-1): Structured data sections populated
4. consistency    (0-1): Narrative agrees with structured data (counts, entities, claims)
5. composite_score: Weighted average of the above
"""

import re


# Concepts expected in a well-formed briefing.
# Each entry is a list of synonyms — the concept is "present" if ANY variant matches.
REQUIRED_CONCEPTS = [
    ["market overview", "tonight", "games", "across"],  # market context
    ["anomal", "stale", "outlier", "flag", "suspicious", "unreliable"],  # anomaly discussion
    ["arbitrage", "arb ", "risk-free", "guaranteed profit"],  # arbitrage coverage
    ["value", "edge", "overlay", "opportunity", "best bet"],  # value analysis
    ["sportsbook", "book", "draftkings", "fanduel", "betmgm", "caesars", "pinnacle", "pointsbet", "bet365"],  # sportsbook mentions
]

# Tool categories the agent should invoke during briefing generation
REQUIRED_TOOL_CATEGORIES = {
    "data": ["get_games", "get_odds_for_game", "get_market_summary"],
    "detection": [
        "run_detection",
        "detect_stale_lines",
        "detect_outlier_odds",
        "detect_arbitrage",
    ],
    "analysis": [
        "run_analysis",
        "analyze_vig",
        "find_best_lines",
        "rank_sportsbooks",
        "find_value_opportunities",
    ],
}


class BriefingEvaluator:
    """Evaluate an agent-generated briefing on multiple quality dimensions."""

    def evaluate(self, briefing_text: str, tool_calls: list[dict],
                 structured_data: dict | None = None) -> dict:
        """
        Score a briefing on completeness, tool coverage, structured data,
        and narrative consistency.

        Args:
            briefing_text: The narrative/markdown briefing text produced by the agent.
            tool_calls: List of tool-call trace dicts ({"tool": ..., "input": ...}).
            structured_data: Optional dict with structured briefing fields
                            (stale_lines, outlier_odds, arbitrage, etc.)

        Returns:
            Dict with individual scores (0-1) and a weighted composite score.
        """
        completeness = self._score_completeness(briefing_text)
        tool_coverage = self._score_tool_coverage(tool_calls)

        scores = {
            "completeness": round(completeness, 4),
            "tool_coverage": round(tool_coverage, 4),
        }

        if structured_data:
            structured_score = self._score_structured_completeness(structured_data)
            consistency = self._score_consistency(briefing_text, structured_data)
            scores["structured_completeness"] = round(structured_score, 4)
            scores["consistency"] = round(consistency, 4)
            composite = (
                completeness * 0.20
                + tool_coverage * 0.20
                + structured_score * 0.30
                + consistency * 0.30
            )
        else:
            composite = (
                completeness * 0.50
                + tool_coverage * 0.50
            )

        scores["composite_score"] = round(composite, 4)
        return scores

    # ── Individual Scorers ────────────────────────────────────────────────────

    def _score_completeness(self, text: str) -> float:
        """Check what fraction of required concepts appear in the briefing."""
        if not text:
            return 0.0

        lower = text.lower()
        found = sum(
            1 for variants in REQUIRED_CONCEPTS
            if any(v in lower for v in variants)
        )
        return found / len(REQUIRED_CONCEPTS)

    def _score_tool_coverage(self, tool_calls: list[dict]) -> float:
        """Check what fraction of required tool categories were invoked."""
        if not tool_calls:
            return 0.0

        called_tool_names = {tc.get("tool", "") for tc in tool_calls}

        categories_covered = 0
        for _category, tool_names in REQUIRED_TOOL_CATEGORIES.items():
            if any(name in called_tool_names for name in tool_names):
                categories_covered += 1

        return categories_covered / len(REQUIRED_TOOL_CATEGORIES)

    def _score_structured_completeness(self, data: dict) -> float:
        """Score how many structured data sections are populated."""
        sections = [
            "stale_lines",
            "outlier_odds",
            "arbitrage",
            "value_plays",
            "sportsbook_rankings",
        ]
        populated = sum(1 for s in sections if len(data.get(s, [])) > 0)
        has_overview = bool(data.get("overview"))
        has_narrative = bool(data.get("narrative"))
        has_quality = bool(data.get("quality_metrics"))

        # 5 data sections + 3 meta sections = 8 total
        total = populated + int(has_overview) + int(has_narrative) + int(has_quality)
        return total / 8


    def _score_consistency(self, text: str, data: dict) -> float:
        """
        Score how well the narrative agrees with the structured data.

        Checks four dimensions (each 0-1, averaged):
        1. Count consistency — mentioned counts match actual data counts
        2. Entity consistency — sportsbooks in narrative exist in data
        3. Presence consistency — narrative doesn't contradict data existence
        4. Number consistency — key numbers in narrative match data values
        """
        if not text or not data:
            return 0.0

        checks: list[float] = []
        lower = text.lower()

        # ── 1. Count consistency ──────────────────────────────────────────
        count_checks = self._check_count_consistency(lower, data)
        if count_checks:
            checks.append(sum(count_checks) / len(count_checks))

        # ── 2. Entity consistency ─────────────────────────────────────────
        entity_score = self._check_entity_consistency(lower, data)
        if entity_score is not None:
            checks.append(entity_score)

        # ── 3. Presence consistency ───────────────────────────────────────
        presence_score = self._check_presence_consistency(lower, data)
        checks.append(presence_score)

        # ── 4. Number consistency ─────────────────────────────────────────
        number_score = self._check_number_consistency(lower, data)
        if number_score is not None:
            checks.append(number_score)

        return sum(checks) / len(checks) if checks else 0.5

    def _check_count_consistency(self, text: str, data: dict) -> list[float]:
        """Check if counts mentioned in narrative match structured data."""
        results = []

        actual_counts = {
            "stale": len(data.get("stale_lines", [])),
            "outlier": len(data.get("outlier_odds", [])),
            "arbitrage": len(data.get("arbitrage", [])),
            "value": len(data.get("value_plays", [])),
        }

        for label, actual in actual_counts.items():
            patterns = [
                rf'(\d+)\s+{label}',
                rf'{label}\S*\s*[:=]\s*(\d+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    mentioned = int(match.group(1))
                    diff = abs(mentioned - actual)
                    results.append(1.0 if diff == 0 else 0.5 if diff == 1 else 0.0)
                    break

        return results

    def _check_entity_consistency(self, text: str, data: dict) -> float | None:
        """Check that sportsbooks mentioned in narrative actually appear in data."""
        data_books = set()
        for section in ["stale_lines", "outlier_odds", "arbitrage", "value_plays", "sportsbook_rankings"]:
            for item in data.get(section, []):
                book = item.get("sportsbook", "") if isinstance(item, dict) else getattr(item, "sportsbook", "")
                if book:
                    data_books.add(book.lower())
                for side_key in ("side_a", "side_b"):
                    side = item.get(side_key, {}) if isinstance(item, dict) else {}
                    if isinstance(side, dict) and side.get("sportsbook"):
                        data_books.add(side["sportsbook"].lower())

        if not data_books:
            return None

        all_known_books = [
            "draftkings", "fanduel", "betmgm", "caesars", "pointsbet",
            "betrivers", "pinnacle", "bet365", "barstool", "wynnbet",
        ]
        mentioned_books = [b for b in all_known_books if b in text]

        if not mentioned_books:
            return None

        correct = sum(1 for b in mentioned_books if b in data_books)
        return correct / len(mentioned_books)

    def _check_presence_consistency(self, text: str, data: dict) -> float:
        """Check narrative doesn't contradict data on presence/absence of findings."""
        checks = []

        negation_patterns = {
            "arbitrage": [r'no\s+(clear\s+)?arbitrage', r'no\s+arb', r'arbitrage.*not found', r'0 arbitrage'],
            "stale": [r'no\s+stale', r'all\s+(lines?\s+)?fresh', r'0 stale'],
            "outlier": [r'no\s+outlier', r'no\s+significant\s+outlier', r'0 outlier'],
        }

        actual_counts = {
            "arbitrage": len(data.get("arbitrage", [])),
            "stale": len(data.get("stale_lines", [])),
            "outlier": len(data.get("outlier_odds", [])),
        }

        for category, patterns in negation_patterns.items():
            claims_none = any(re.search(p, text) for p in patterns)
            has_data = actual_counts[category] > 0

            if claims_none and has_data:
                checks.append(0.0)
            else:
                checks.append(1.0)

        return sum(checks) / len(checks) if checks else 1.0

    def _check_number_consistency(self, text: str, data: dict) -> float | None:
        """Check that key numbers in narrative match structured data values."""
        matches = 0
        total = 0

        data_numbers = set()

        for arb in data.get("arbitrage", []):
            if isinstance(arb, dict):
                pct = arb.get("profit_pct")
                if pct is not None:
                    data_numbers.add(round(float(pct), 2))
                    data_numbers.add(round(float(pct), 1))

        for vp in data.get("value_plays", []):
            if isinstance(vp, dict):
                edge = vp.get("edge_pct")
                if edge is not None:
                    data_numbers.add(round(float(edge), 2))
                    data_numbers.add(round(float(edge), 1))

        for rank in data.get("sportsbook_rankings", []):
            if isinstance(rank, dict):
                vig = rank.get("avg_vig_pct")
                if vig is not None:
                    data_numbers.add(round(float(vig), 2))
                    data_numbers.add(round(float(vig), 1))

        if not data_numbers:
            return None

        pct_matches = re.findall(r'(\d+\.?\d*)\s*%', text)
        for m in pct_matches:
            val = float(m)
            total += 1
            if any(abs(val - dn) < 0.15 for dn in data_numbers):
                matches += 1

        if total == 0:
            return None

        return matches / total
