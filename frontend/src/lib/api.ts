const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 60000): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${body || res.statusText}`);
    }
    return res;
  } catch (error) {
    clearTimeout(timeout);
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw error;
  }
}

export async function triggerBriefing(): Promise<{ message: string; status: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/briefing/trigger`, { method: "POST" });
  return res.json();
}

export async function getBriefingStatus(): Promise<{
  status: string;
  briefing: BriefingResult | null;
  error: string | null;
}> {
  const res = await fetchWithTimeout(`${API_BASE}/api/briefing/status`, {}, 10000);
  return res.json();
}

export async function sendChat(
  message: string,
  history: { role: string; content: string }[]
): Promise<ReadableStream<Uint8Array> | null> {
  const res = await fetchWithTimeout(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, stream: true }),
  }, 120000);
  return res.body;
}

export async function sendChatSync(
  message: string,
  history: { role: string; content: string }[]
): Promise<{ response: string; tool_calls: ToolCall[]; duration_seconds: number }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, stream: false }),
  }, 120000);
  return res.json();
}

export async function uploadData(data: unknown): Promise<{ message: string; games: number; sportsbooks: string[] }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/data/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function resetData(): Promise<{ message: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/data/reset`, { method: "POST" });
  return res.json();
}

export async function loadAltData(): Promise<{ message: string; games: number; sportsbooks: string[] }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/data/load-alt`, { method: "POST" });
  return res.json();
}

export async function getDataGames(): Promise<{ games: { game_id: string; sport: string; home_team: string; away_team: string }[]; count: number }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/data/games`, {}, 10000);
  return res.json();
}

export async function healthCheck(): Promise<{
  status: string;
  api_key_configured: boolean;
  model: string;
}> {
  const res = await fetchWithTimeout(`${API_BASE}/health`, {}, 5000);
  return res.json();
}

export function streamBriefingProgress(
  onToolCall: (tool: string, input: Record<string, unknown>) => void,
  onDone: (status: string) => void,
): () => void {
  let eventSource: EventSource | null = null;
  let retryCount = 0;
  let closed = false;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  const maxRetries = 3;

  const connect = () => {
    if (closed) return;
    eventSource = new EventSource(`${API_BASE}/api/briefing/stream`);

    eventSource.onmessage = (event) => {
      retryCount = 0;
      const data = JSON.parse(event.data);
      if (data.type === "tool_call") {
        onToolCall(data.tool, data.input);
      } else if (data.type === "done") {
        onDone(data.status);
        eventSource?.close();
        closed = true;
      }
    };

    eventSource.onerror = () => {
      eventSource?.close();
      if (!closed && retryCount < maxRetries) {
        retryCount++;
        reconnectTimeout = setTimeout(connect, Math.min(1000 * Math.pow(2, retryCount), 5000));
      }
    };
  };

  connect();
  return () => {
    closed = true;
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
    eventSource?.close();
  };
}

export async function evaluateBriefing(): Promise<EvaluationResult> {
  const res = await fetchWithTimeout(`${API_BASE}/api/briefing/evaluate`, {}, 15000);
  return res.json();
}

// Types

export interface EvaluationResult {
  generated_at: string | null;
  duration_seconds: number | null;
  scores: {
    completeness: number;
    tool_coverage: number;
    anomaly_recall: number;
    structured_completeness?: number;
    consistency?: number;
    composite_score: number;
  };
  quality_metrics: QualityMetrics | null;
}
export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
}

export interface StaleLineAlert {
  game_id: string;
  home_team: string;
  away_team: string;
  sportsbook: string;
  minutes_behind: number;
  hours_behind: number;
  severity: string;
  confidence_score: number;
  confidence_level: string;
  explanation: string;
}

export interface OutlierAlert {
  game_id: string;
  home_team: string;
  away_team: string;
  sportsbook: string;
  market: string;
  value: number | null;
  odds: number | null;
  consensus_median: number | null;
  deviation: number | null;
  z_score: number;
  severity: string;
  confidence_score: number;
  confidence_level: string;
  explanation: string;
}

export interface ArbitrageSide {
  label: string;
  sportsbook: string;
  odds: number;
  implied_probability: number;
  stake_on_1000: number;
}

export interface ArbitrageOpportunity {
  game_id: string;
  home_team: string;
  away_team: string;
  market: string;
  side_a: ArbitrageSide;
  side_b: ArbitrageSide;
  combined_implied: number;
  profit_pct: number;
  profit_on_1000: number;
  confidence_score: number;
  confidence_level: string;
  explanation: string;
}

export interface ValuePlay {
  game_id: string;
  home_team: string;
  away_team: string;
  market: string;
  side: string;
  sportsbook: string;
  odds: number;
  edge_pct: number;
  implied_prob: number;
  payout_on_100: number;
  confidence: string;
}

export interface SportsbookRanking {
  rank: number;
  sportsbook: string;
  composite_score: number;
  grade: string;
  avg_vig_pct: number;
  stale_flags: number;
  outlier_flags: number;
  games_covered: number;
}

export interface MarketOverview {
  total_games: number;
  total_sportsbooks: number;
  total_anomalies: number;
  stale_count: number;
  outlier_count: number;
  arbitrage_count: number;
}

export interface QualityMetrics {
  overall_confidence: number;
  high_confidence_pct: number;
  total_alerts: number;
  high_confidence_alerts: number;
  data_warnings: string[];
}

export interface BriefingResult {
  overview: MarketOverview;
  stale_lines: StaleLineAlert[];
  outlier_odds: OutlierAlert[];
  arbitrage: ArbitrageOpportunity[];
  value_plays: ValuePlay[];
  sportsbook_rankings: SportsbookRanking[];
  narrative: string;
  quality_metrics: QualityMetrics;
  generated_at: string;
  duration_seconds: number;
  tool_calls: ToolCall[];
  tools_used_count: number;
}
