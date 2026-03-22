/** Shared tool label mappings and stage classification used by both page.tsx and ToolCallTrace. */

export const TOOL_LABELS: Record<string, string> = {
  get_games: "Fetching game list",
  get_odds_for_game: "Loading odds data",
  get_market_summary: "Building market summary",
  get_market_summary_tool: "Building market summary",
  run_detection: "Running anomaly detection",
  detect_stale_lines_tool: "Checking for stale lines",
  detect_outlier_odds_tool: "Detecting outlier odds",
  detect_arbitrage_tool: "Scanning for arbitrage",
  run_analysis: "Running full market analysis",
  analyze_vig: "Calculating vig/margins",
  find_best_lines_tool: "Finding best available lines",
  rank_sportsbooks_tool: "Ranking sportsbooks",
  find_value_opportunities_tool: "Identifying value opportunities",
  calculate_implied_probability: "Computing implied probability",
  calculate_vig_tool: "Computing vig",
  calculate_fair_odds: "Computing fair odds",
  check_arbitrage_tool: "Checking arbitrage math",
  // Structured briefing pipeline steps
  detect_stale_lines: "Checking for stale lines",
  detect_outlier_odds: "Detecting outlier odds",
  detect_arbitrage: "Scanning for arbitrage",
  find_best_lines: "Finding best available lines",
  rank_sportsbooks: "Ranking sportsbooks",
  find_value_opportunities: "Identifying value opportunities",
  build_structured_models: "Building structured data models",
  generate_narrative: "Writing executive summary (LLM)",
};

export function getToolStage(tool: string): string {
  if (["get_games", "get_odds_for_game", "get_market_summary", "get_market_summary_tool"].includes(tool)) return "Data Collection";
  if (["run_detection", "detect_stale_lines", "detect_stale_lines_tool", "detect_outlier_odds", "detect_outlier_odds_tool", "detect_arbitrage", "detect_arbitrage_tool"].includes(tool)) return "Anomaly Detection";
  if (["run_analysis", "analyze_vig", "find_best_lines", "find_best_lines_tool", "rank_sportsbooks", "rank_sportsbooks_tool", "find_value_opportunities", "find_value_opportunities_tool", "build_structured_models"].includes(tool)) return "Market Analysis";
  if (["calculate_implied_probability", "calculate_vig_tool", "calculate_fair_odds", "check_arbitrage_tool"].includes(tool)) return "Calculations";
  if (["generate_narrative"].includes(tool)) return "Market Analysis";
  return "Processing";
}

export function getToolColor(tool: string): string {
  if (tool.includes("detect") || tool.includes("Detection")) return "bg-red-50 text-red-700 border-red-200";
  if (tool.includes("analysis") || tool.includes("analyze") || tool.includes("vig")) return "bg-purple-50 text-purple-700 border-purple-200";
  if (tool.includes("arbitrage")) return "bg-amber-50 text-amber-700 border-amber-200";
  if (tool.includes("rank")) return "bg-green-50 text-green-700 border-green-200";
  if (tool.includes("value")) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (tool.includes("best_lines")) return "bg-blue-50 text-blue-700 border-blue-200";
  if (tool.includes("games") || tool.includes("odds") || tool.includes("market")) return "bg-sky-50 text-sky-700 border-sky-200";
  if (tool.includes("calculate") || tool.includes("fair")) return "bg-indigo-50 text-indigo-700 border-indigo-200";
  return "bg-gray-50 text-gray-700 border-gray-200";
}
