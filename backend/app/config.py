"""Application configuration via environment variables."""

import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # LLM Configuration — Direct Anthropic API
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    model_id: str = Field(default="claude-sonnet-4-20250514", alias="MODEL_ID")
    max_tokens: int = Field(default=8192, alias="MAX_TOKENS")

    # Rate limiting
    rate_limit_max: int = Field(default=30, alias="RATE_LIMIT_MAX")
    rate_limit_window: int = Field(default=3600, alias="RATE_LIMIT_WINDOW")

    # Application
    app_name: str = "Betstamp AI Odds Agent"
    debug: bool = Field(default=False, alias="DEBUG")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    # Detection thresholds (tunable)
    stale_threshold_minutes: int = Field(default=120, alias="STALE_THRESHOLD_MINUTES")
    outlier_z_threshold: float = Field(default=2.0, alias="OUTLIER_Z_THRESHOLD")
    min_edge_pct: float = Field(default=1.0, alias="MIN_EDGE_PCT")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
