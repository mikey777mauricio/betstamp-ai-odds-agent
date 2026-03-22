"""
Odds Agent — Strands SDK agent for briefing generation and follow-up chat.

Two modes:
1. generate_briefing(): Runs the 3-stage pipeline (detect -> analyze -> brief)
2. chat(): Answers follow-up questions grounded in tools
"""

import json
import time
import logging
import threading
from datetime import datetime, timezone
from typing import AsyncGenerator

from strands import Agent
from strands.models.anthropic import AnthropicModel

from app.config import settings
from app.agent.prompts import BRIEFING_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT, NARRATIVE_SYSTEM_PROMPT
from app.agent.tools import BRIEFING_TOOLS, CHAT_TOOLS, clear_tool_trace, get_tool_trace, set_chat_trace
from app.agent.tools.trace import _log_tool_call
from app.eval.evaluator import REQUIRED_TOOL_CATEGORIES
from app.models.briefing import (
    StructuredBriefing, MarketOverview, StaleLineAlert, OutlierAlert,
    ArbitrageOpportunity, ArbitrageSide, ValuePlay, SportsbookRanking,
    QualityMetrics,
)
from app.data.store import odds_store as data_store
from app.tools.detection_tools import run_all_detection
from app.tools.analysis_tools import run_full_analysis, rank_sportsbooks
from app.tools.math_utils import american_to_decimal

logger = logging.getLogger(__name__)


def _build_model():
    """Build the Anthropic LLM model."""
    logger.info(f"Using Anthropic API model: {settings.model_id}")
    return AnthropicModel(
        client_args={"api_key": settings.anthropic_api_key},
        model_id=settings.model_id,
        max_tokens=settings.max_tokens,
    )


def _build_briefing_context_summary(briefing: dict) -> str:
    """Build a rich context summary from the last briefing for chat mode.

    Includes full structured findings so the chat agent can answer detailed
    follow-up questions without needing to re-run every tool.
    """
    parts = []
    parts.append(f"Briefing generated at {briefing.get('generated_at', 'unknown')}.")

    overview = briefing.get("overview", {})
    if overview:
        parts.append(
            f"Analyzed {overview.get('total_games', 0)} games across "
            f"{overview.get('total_sportsbooks', 0)} sportsbooks. "
            f"Found {overview.get('total_anomalies', 0)} anomalies: "
            f"{overview.get('stale_count', 0)} stale, "
            f"{overview.get('outlier_count', 0)} outliers, "
            f"{overview.get('arbitrage_count', 0)} arbitrage."
        )

    # Include full stale line details
    stale = briefing.get("stale_lines", [])
    if stale:
        parts.append("\n### Stale Lines Detected:")
        for s in stale:
            if isinstance(s, dict):
                parts.append(
                    f"- {s.get('sportsbook', '')} on {s.get('away_team', '')} @ {s.get('home_team', '')} "
                    f"(game {s.get('game_id', '')}): {s.get('hours_behind', 0)} hours behind, "
                    f"severity={s.get('severity', '')}, confidence={s.get('confidence_level', '')} "
                    f"({s.get('confidence_score', 0):.0%}). {s.get('explanation', '')}"
                )

    # Include full outlier details
    outliers = briefing.get("outlier_odds", [])
    if outliers:
        parts.append("\n### Outlier Odds Detected:")
        for o in outliers:
            if isinstance(o, dict):
                parts.append(
                    f"- {o.get('sportsbook', '')} on {o.get('away_team', '')} @ {o.get('home_team', '')} "
                    f"({o.get('market', '')}): z-score={o.get('z_score', 0):.1f}, "
                    f"severity={o.get('severity', '')}, confidence={o.get('confidence_level', '')}. "
                    f"{o.get('explanation', '')}"
                )

    # Include full arbitrage details
    arbs = briefing.get("arbitrage", [])
    if arbs:
        parts.append("\n### Arbitrage Opportunities:")
        for a in arbs:
            if isinstance(a, dict):
                sa = a.get("side_a", {})
                sb = a.get("side_b", {})
                parts.append(
                    f"- {a.get('away_team', '')} @ {a.get('home_team', '')} ({a.get('market', '')}): "
                    f"{a.get('profit_pct', 0):.2f}% profit. "
                    f"Side A: {sa.get('label', '')} at {sa.get('sportsbook', '')} ({sa.get('odds', '')}), "
                    f"Side B: {sb.get('label', '')} at {sb.get('sportsbook', '')} ({sb.get('odds', '')}). "
                    f"${a.get('profit_on_1000', 0):.2f} guaranteed on $1000."
                )

    # Include narrative summary
    narrative = briefing.get("narrative", "")
    if narrative:
        parts.append(f"\n### Executive Summary:\n{narrative}")

    parts.append(
        "\nThe data is still loaded in the system. Use your tools to look up "
        "specific games, odds, or re-verify any finding the user asks about."
    )
    return "\n".join(parts)


class OddsAgent:
    """Manages the Strands agent for odds analysis."""

    def __init__(self):
        self._briefing_context: list[dict] = []
        self._last_briefing: dict | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _verify_tool_coverage(tool_calls: list[dict]) -> tuple[bool, list[str]]:
        """
        Check which required tool categories were covered.

        Returns:
            (tools_verified, missing_categories) — True if all categories covered.
        """
        called_names = {tc.get("tool", "") for tc in tool_calls}
        missing = []

        for category, tool_names in REQUIRED_TOOL_CATEGORIES.items():
            if not any(name in called_names for name in tool_names):
                missing.append(category)

        return (len(missing) == 0, missing)

    def generate_briefing(self) -> dict:
        """
        Generate a full daily market briefing.

        The agent:
        1. Queries the data to understand the slate
        2. Runs detection tools to find anomalies
        3. Runs analysis tools for vig, best lines, rankings
        4. Synthesizes everything into a structured briefing
        """
        start = time.time()
        clear_tool_trace()

        model = _build_model()
        agent = Agent(
            model=model,
            system_prompt=BRIEFING_SYSTEM_PROMPT,
            tools=BRIEFING_TOOLS,
        )

        user_prompt = (
            "Generate the daily market briefing for today's slate. "
            "Follow the exact briefing structure specified. "
            "Use your tools to get ALL the data — do not skip any section. "
            "Show your math and reference which tools produced each number."
        )

        result = agent(user_prompt)
        duration = round(time.time() - start, 2)

        # Extract the text response
        briefing_text = str(result)

        # Get tool usage from our trace wrapper
        tool_calls = get_tool_trace()

        # Verify tool coverage across required categories
        tools_verified, missing_categories = self._verify_tool_coverage(tool_calls)
        if missing_categories:
            logger.warning(
                f"Briefing missing tool categories: {missing_categories}. "
                f"The agent may have skipped required analysis steps."
            )

        # Store context for follow-up chat
        self._briefing_context = agent.messages.copy() if hasattr(agent, "messages") else []
        result = {
            "briefing": briefing_text,
            "tool_calls": tool_calls,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": duration,
            "tools_used_count": len(tool_calls),
            "tools_verified": tools_verified,
            "missing_categories": missing_categories,
        }
        with self._lock:
            self._last_briefing = result

        return result

    def chat(self, message: str, conversation_history: list[dict] | None = None) -> dict:
        """
        Handle a follow-up question about the briefing.

        Uses the full tool suite so the agent can drill into any aspect.
        Per-request trace list prevents concurrent chat requests from interleaving.
        """
        start = time.time()
        request_trace: list[dict] = []
        set_chat_trace(request_trace)

        model = _build_model()

        # Build context-aware system prompt with rich briefing summary
        system_prompt = CHAT_SYSTEM_PROMPT
        with self._lock:
            briefing = self._last_briefing
        if briefing:
            system_prompt += "\n\n## Previous Briefing Context\n" + _build_briefing_context_summary(briefing)

        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=CHAT_TOOLS,
        )

        # Replay conversation history if provided
        if conversation_history:
            for msg in conversation_history:
                if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                    logger.warning(f"Skipping malformed conversation message: {msg}")
                    continue
                if hasattr(agent, "messages"):
                    agent.messages.append(msg)

        try:
            result = agent(message)
            duration = round(time.time() - start, 2)
            return {
                "response": str(result),
                "tool_calls": list(request_trace),
                "duration_seconds": duration,
            }
        finally:
            set_chat_trace(None)

    async def chat_stream(
        self, message: str, conversation_history: list[dict] | None = None
    ) -> AsyncGenerator[dict, None]:
        """
        Stream a chat response using Strands stream_async for real-time events.

        Yields events:
        - {"type": "tool_call", "tool": "...", "input": {...}}
        - {"type": "text", "content": "..."}
        - {"type": "done", "duration": 1.23}
        """
        start = time.time()
        request_trace: list[dict] = []
        set_chat_trace(request_trace)

        model = _build_model()

        system_prompt = CHAT_SYSTEM_PROMPT
        with self._lock:
            briefing = self._last_briefing
        if briefing:
            system_prompt += "\n\n## Previous Briefing Context\n" + _build_briefing_context_summary(briefing)

        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=CHAT_TOOLS,
        )

        if conversation_history:
            for msg in conversation_history:
                if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                    logger.warning(f"Skipping malformed conversation message: {msg}")
                    continue
                if hasattr(agent, "messages"):
                    agent.messages.append(msg)

        # Use Strands stream_async for true event streaming
        tool_calls_yielded = 0
        try:
            async for event in agent.stream_async(message):
                # Check for new tool calls from our trace
                while tool_calls_yielded < len(request_trace):
                    tc = request_trace[tool_calls_yielded]
                    yield {"type": "tool_call", "tool": tc["tool"], "input": tc["input"]}
                    tool_calls_yielded += 1

                # Yield text chunks as they arrive
                if "data" in event and event["data"]:
                    yield {"type": "text", "content": event["data"]}
        except Exception as e:
            logger.error(f"Chat stream error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
        finally:
            # Yield any remaining tool calls before cleanup
            while tool_calls_yielded < len(request_trace):
                tc = request_trace[tool_calls_yielded]
                yield {"type": "tool_call", "tool": tc["tool"], "input": tc["input"]}
                tool_calls_yielded += 1

            set_chat_trace(None)
            duration = round(time.time() - start, 2)
            yield {"type": "done", "duration": duration, "tools_used": len(request_trace)}

    def generate_structured_briefing(self) -> dict:
        """
        Generate a structured briefing by running tools directly,
        then asking the LLM for narrative analysis only.

        Each stage is wrapped in try/except for graceful degradation —
        a partial briefing is better than no briefing.
        """
        start = time.time()
        clear_tool_trace()
        data_warnings: list[str] = []

        # --- Pre-flight check ---
        games = data_store.get_games()
        if not games:
            logger.error("Cannot generate briefing: no data loaded")
            raise ValueError("No odds data loaded. Upload data via /api/data/upload first.")

        logger.info(f"Starting structured briefing for {len(games)} games")
        _log_tool_call("get_games", {"count": len(games)})

        # --- Stage 1: Run detection tools (with graceful degradation) ---
        try:
            logger.info("Stage 1: Running detection tools...")
            _log_tool_call("detect_stale_lines", {})
            _log_tool_call("detect_outlier_odds", {})
            _log_tool_call("detect_arbitrage", {})
            detection = run_all_detection()
        except Exception as e:
            logger.error(f"Detection stage failed: {e}", exc_info=True)
            data_warnings.append(f"Detection partially failed: {e}")
            detection = {
                "stale_lines": [], "outlier_odds": [], "arbitrage_opportunities": [],
                "summary": {"total_anomalies": 0, "stale_count": 0, "outlier_count": 0, "arbitrage_count": 0},
            }

        # --- Stage 2: Run analysis tools (with graceful degradation) ---
        try:
            logger.info("Stage 2: Running analysis tools...")
            _log_tool_call("analyze_vig", {})
            _log_tool_call("find_best_lines", {})
            _log_tool_call("find_value_opportunities", {})
            analysis = run_full_analysis()
        except Exception as e:
            logger.error(f"Analysis stage failed: {e}", exc_info=True)
            data_warnings.append(f"Analysis partially failed: {e}")
            analysis = {"games_analyzed": 0, "value_opportunities": []}

        try:
            _log_tool_call("rank_sportsbooks", {})
            rankings = rank_sportsbooks()
        except Exception as e:
            logger.error(f"Sportsbook ranking failed: {e}", exc_info=True)
            data_warnings.append(f"Rankings failed: {e}")
            rankings = []

        # --- Stage 3: Build structured data (safe mapping) ---
        logger.info("Stage 3: Building structured models...")
        _log_tool_call("build_structured_models", {"stale": len(detection.get("stale_lines", [])), "outliers": len(detection.get("outlier_odds", [])), "arbs": len(detection.get("arbitrage_opportunities", []))})
        stale_lines = []
        for s in detection.get("stale_lines", []):
            try:
                stale_lines.append(StaleLineAlert(
                    game_id=s["game_id"],
                    home_team=s["home_team"],
                    away_team=s["away_team"],
                    sportsbook=s["sportsbook"],
                    minutes_behind=s["minutes_behind"],
                    hours_behind=s["hours_behind"],
                    severity=s["severity"],
                    confidence_score=s.get("confidence", {}).get("score", 0.5),
                    confidence_level=s.get("confidence", {}).get("level", "medium"),
                    explanation=s.get("explanation", ""),
                ))
            except Exception as e:
                logger.warning(f"Skipped stale line alert: {e}")
                data_warnings.append(f"Skipped stale line: {e}")

        outlier_odds = []
        for o in detection.get("outlier_odds", []):
            try:
                outlier_odds.append(OutlierAlert(
                    game_id=o["game_id"],
                    home_team=o["home_team"],
                    away_team=o["away_team"],
                    sportsbook=o["sportsbook"],
                    market=o["market"],
                    value=o.get("value"),
                    odds=o.get("odds"),
                    consensus_median=o.get("consensus_median") or o.get("consensus_median_prob"),
                    deviation=o.get("deviation") or o.get("deviation_prob"),
                    z_score=o.get("z_score", 0),
                    severity=o.get("severity", "unknown"),
                    confidence_score=o.get("confidence", {}).get("score", 0.5),
                    confidence_level=o.get("confidence", {}).get("level", "medium"),
                    explanation=o.get("explanation", ""),
                ))
            except Exception as e:
                logger.warning(f"Skipped outlier alert: {e}")
                data_warnings.append(f"Skipped outlier: {e}")

        arbitrage = []
        for arb in detection.get("arbitrage_opportunities", []):
            try:
                profit_pct = arb["profit_pct"]
                odds_a = arb["side_a"]["odds"]
                odds_b = arb["side_b"]["odds"]
                dec_a = american_to_decimal(odds_a)
                dec_b = american_to_decimal(odds_b)
                total_inv = (1 / dec_a) + (1 / dec_b)
                if total_inv <= 0:
                    continue  # Skip invalid arbitrage
                stake_a = round(1000 * (1 / dec_a) / total_inv, 2)
                stake_b = round(1000.00 - stake_a, 2)  # Guarantee sum = $1000
                profit_dollars = round(1000 * profit_pct / 100, 2)

                arbitrage.append(ArbitrageOpportunity(
                    game_id=arb["game_id"],
                    home_team=arb["home_team"],
                    away_team=arb["away_team"],
                    market=arb["market"],
                    side_a=ArbitrageSide(
                        label=arb["side_a"]["label"],
                        sportsbook=arb["side_a"]["sportsbook"],
                        odds=arb["side_a"]["odds"],
                        implied_probability=arb["side_a"]["implied_probability"],
                        stake_on_1000=stake_a,
                    ),
                    side_b=ArbitrageSide(
                        label=arb["side_b"]["label"],
                        sportsbook=arb["side_b"]["sportsbook"],
                        odds=arb["side_b"]["odds"],
                        implied_probability=arb["side_b"]["implied_probability"],
                        stake_on_1000=stake_b,
                    ),
                    combined_implied=arb["combined_implied"],
                    profit_pct=profit_pct,
                    profit_on_1000=profit_dollars,
                    confidence_score=arb.get("confidence", {}).get("score", 0.5),
                    confidence_level=arb.get("confidence", {}).get("level", "medium"),
                    explanation=arb.get("explanation", ""),
                ))
            except Exception as e:
                logger.warning(f"Skipped arbitrage opportunity: {e}")
                data_warnings.append(f"Skipped arbitrage: {e}")

        value_plays = []
        for v in analysis.get("value_opportunities", []):
            try:
                value_plays.append(ValuePlay(
                    game_id=v["game_id"],
                    home_team=v["home_team"],
                    away_team=v["away_team"],
                    market=v["market"],
                    side=v["side"],
                    sportsbook=v["sportsbook"],
                    odds=v["odds"],
                    edge_pct=v["edge_pct"],
                    implied_prob=v["implied_prob"],
                    payout_on_100=v["payout_on_100"],
                    confidence=v.get("confidence", "medium"),
                ))
            except Exception as e:
                logger.warning(f"Skipped value play: {e}")
                data_warnings.append(f"Skipped value play: {e}")

        sportsbook_rankings = []
        for r in rankings:
            try:
                sportsbook_rankings.append(SportsbookRanking(
                    rank=r["rank"],
                    sportsbook=r["sportsbook"],
                    composite_score=r["composite_score"],
                    grade=r["grade"],
                    avg_vig_pct=r["avg_vig_pct"],
                    stale_flags=r["stale_flags"],
                    outlier_flags=r["outlier_flags"],
                    games_covered=r["games_covered"],
                ))
            except Exception as e:
                logger.warning(f"Skipped sportsbook ranking: {e}")
                data_warnings.append(f"Skipped ranking: {e}")

        overview = MarketOverview(
            total_games=analysis.get("games_analyzed", 0),
            total_sportsbooks=len(rankings),
            total_anomalies=detection.get("summary", {}).get("total_anomalies", 0),
            stale_count=detection.get("summary", {}).get("stale_count", 0),
            outlier_count=detection.get("summary", {}).get("outlier_count", 0),
            arbitrage_count=detection.get("summary", {}).get("arbitrage_count", 0),
        )

        # --- Stage 4: Quality metrics ---
        all_alerts = stale_lines + outlier_odds + arbitrage
        if all_alerts:
            scores = [a.confidence_score for a in all_alerts]
            avg_conf = sum(scores) / len(scores)
            high_count = sum(1 for a in all_alerts if a.confidence_level == "high")
        else:
            avg_conf = 0.0
            high_count = 0

        quality = QualityMetrics(
            overall_confidence=round(avg_conf, 2),
            high_confidence_pct=round(high_count / max(len(all_alerts), 1), 2),
            total_alerts=len(all_alerts),
            high_confidence_alerts=high_count,
            data_warnings=data_warnings,
        )

        # --- Stage 5: Ask LLM for narrative analysis only ---
        logger.info("Stage 5: Generating narrative summary...")
        _log_tool_call("generate_narrative", {"model": settings.model_id})
        try:
            model = _build_model()
            agent = Agent(
                model=model,
                system_prompt=NARRATIVE_SYSTEM_PROMPT,
                tools=[],
            )

            data_summary = json.dumps({
                "overview": overview.model_dump(),
                "stale_lines": [s.model_dump() for s in stale_lines],
                "outlier_odds": [o.model_dump() for o in outlier_odds],
                "arbitrage": [a.model_dump() for a in arbitrage],
                "value_plays": [v.model_dump() for v in value_plays],
                "top_3_books": [r.model_dump() for r in sportsbook_rankings[:3]],
                "bottom_2_books": [r.model_dump() for r in sportsbook_rankings[-2:]],
            }, indent=2)

            narrative_prompt = (
                "Here is the structured data from today's odds analysis. "
                "Write a concise executive summary (3-5 paragraphs) highlighting "
                "the key findings, actionable insights, and what to watch. "
                "Do NOT repeat the raw data — the UI already displays that. "
                "Focus on WHY these findings matter and WHAT to do about them.\n\n"
                f"{data_summary}"
            )

            result = agent(narrative_prompt)
            narrative = str(result)

            # Validate narrative
            if not narrative or len(narrative.strip()) < 50:
                logger.warning(f"Narrative too short ({len(narrative)} chars), using fallback")
                narrative = (
                    f"Today's analysis covered {overview.total_games} games across "
                    f"{overview.total_sportsbooks} sportsbooks with "
                    f"{overview.total_anomalies} anomalies detected."
                )
            elif len(narrative) > 3000:
                logger.warning(f"Narrative too long ({len(narrative)} chars), truncating")
                narrative = narrative[:2500] + "\n\n[Summary truncated for brevity]"

        except Exception as e:
            logger.error(f"Narrative generation failed: {e}", exc_info=True)
            data_warnings.append(f"Narrative generation failed: {e}")
            narrative = (
                f"Today's analysis covered {overview.total_games} games across "
                f"{overview.total_sportsbooks} sportsbooks. "
                f"{overview.total_anomalies} anomalies were detected. "
                "See the structured data below for details."
            )

        duration = round(time.time() - start, 2)
        tool_calls = get_tool_trace()

        tools_verified, missing_categories = self._verify_tool_coverage(tool_calls)

        structured = StructuredBriefing(
            overview=overview,
            stale_lines=stale_lines,
            outlier_odds=outlier_odds,
            arbitrage=arbitrage,
            value_plays=value_plays,
            sportsbook_rankings=sportsbook_rankings,
            narrative=narrative,
            quality_metrics=quality,
            generated_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=duration,
            tool_calls=tool_calls,
        )

        result = {
            **structured.model_dump(),
            "tools_used_count": len(tool_calls),
            "tools_verified": tools_verified,
            "missing_categories": missing_categories,
        }
        with self._lock:
            self._last_briefing = result

        logger.info(
            f"Briefing complete: {duration}s, {len(tool_calls)} tools, "
            f"{overview.total_anomalies} anomalies, quality={quality.overall_confidence:.0%}"
        )
        return result

    @property
    def last_briefing(self) -> dict | None:
        with self._lock:
            return self._last_briefing


# Singleton
odds_agent = OddsAgent()
