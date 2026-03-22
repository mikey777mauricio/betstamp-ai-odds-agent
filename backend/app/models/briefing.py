"""Structured briefing output models.

Instead of relying on the LLM to format markdown, we capture tool outputs
directly into typed models. The LLM adds narrative summaries only.
"""

from pydantic import BaseModel, field_validator


class StaleLineAlert(BaseModel):
    game_id: str
    home_team: str
    away_team: str
    sportsbook: str
    minutes_behind: float
    hours_behind: float
    severity: str
    confidence_score: float
    confidence_level: str
    explanation: str

    @field_validator("confidence_score")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class OutlierAlert(BaseModel):
    game_id: str
    home_team: str
    away_team: str
    sportsbook: str
    market: str
    value: float | None = None
    odds: int | None = None
    consensus_median: float | None = None
    deviation: float | None = None
    z_score: float
    severity: str
    confidence_score: float
    confidence_level: str
    explanation: str

    @field_validator("confidence_score")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class ArbitrageSide(BaseModel):
    label: str
    sportsbook: str
    odds: int
    implied_probability: float
    stake_on_1000: float  # How much to bet on $1000 total


class ArbitrageOpportunity(BaseModel):
    game_id: str
    home_team: str
    away_team: str
    market: str
    side_a: ArbitrageSide
    side_b: ArbitrageSide
    combined_implied: float
    profit_pct: float
    profit_on_1000: float  # Dollar profit on $1000 total stake
    confidence_score: float
    confidence_level: str
    explanation: str

    @field_validator("confidence_score")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class ValuePlay(BaseModel):
    game_id: str
    home_team: str
    away_team: str
    market: str
    side: str
    sportsbook: str
    odds: int
    edge_pct: float
    implied_prob: float
    payout_on_100: float
    confidence: str


class SportsbookRanking(BaseModel):
    rank: int
    sportsbook: str
    composite_score: float
    grade: str
    avg_vig_pct: float
    stale_flags: int
    outlier_flags: int
    games_covered: int

    @field_validator("composite_score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(0.0, min(100.0, v))


class MarketOverview(BaseModel):
    total_games: int
    total_sportsbooks: int
    total_anomalies: int
    stale_count: int
    outlier_count: int
    arbitrage_count: int


class QualityMetrics(BaseModel):
    """Aggregate quality metrics for the briefing."""
    overall_confidence: float
    high_confidence_pct: float
    total_alerts: int
    high_confidence_alerts: int
    data_warnings: list[str] = []


class StructuredBriefing(BaseModel):
    """The complete structured briefing — deterministic data from tools."""
    overview: MarketOverview
    stale_lines: list[StaleLineAlert]
    outlier_odds: list[OutlierAlert]
    arbitrage: list[ArbitrageOpportunity]
    value_plays: list[ValuePlay]
    sportsbook_rankings: list[SportsbookRanking]
    narrative: str  # LLM-generated summary/analysis
    quality_metrics: QualityMetrics
    generated_at: str
    duration_seconds: float
    tool_calls: list[dict]
