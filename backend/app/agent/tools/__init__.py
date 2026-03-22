"""
Strands @tool wrappers for the odds agent.

These wrap the deterministic Python functions from app.tools.*
and expose them as callable tools for the LLM agent.

The agent calls these tools; the tools return structured JSON.
The agent NEVER does math itself — these tools do all the computation.
"""

from app.agent.tools.trace import (
    clear_tool_trace,
    set_chat_trace,
    get_tool_trace,
    get_tool_trace_since,
)

from app.agent.tools.data_tools import (
    get_games,
    get_odds_for_game,
    get_market_summary_tool,
)

from app.agent.tools.detection_tools import (
    run_detection,
    detect_stale_lines_tool,
    detect_outlier_odds_tool,
    detect_arbitrage_tool,
)

from app.agent.tools.analysis_tools import (
    run_analysis,
    analyze_vig,
    find_best_lines_tool,
    rank_sportsbooks_tool,
    find_value_opportunities_tool,
)

from app.agent.tools.math_tools import (
    calculate_implied_probability,
    calculate_vig_tool,
    calculate_fair_odds,
    check_arbitrage_tool,
)


# ─── Tool Collections ──────────────────────────────────────────────────────────

ALL_TOOLS = [
    # Data
    get_games,
    get_odds_for_game,
    get_market_summary_tool,
    # Detection
    run_detection,
    detect_stale_lines_tool,
    detect_outlier_odds_tool,
    detect_arbitrage_tool,
    # Analysis
    run_analysis,
    analyze_vig,
    find_best_lines_tool,
    rank_sportsbooks_tool,
    find_value_opportunities_tool,
    # Math
    calculate_implied_probability,
    calculate_vig_tool,
    calculate_fair_odds,
    check_arbitrage_tool,
]

# Briefing mode gets the high-level tools (agent decides sequence)
BRIEFING_TOOLS = [
    get_games,
    get_market_summary_tool,
    run_detection,
    run_analysis,
    find_value_opportunities_tool,
    rank_sportsbooks_tool,
    detect_arbitrage_tool,
]

# Chat mode gets all tools for flexible drill-down
CHAT_TOOLS = ALL_TOOLS
