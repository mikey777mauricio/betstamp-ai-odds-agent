"""
Betstamp AI Odds Agent — FastAPI Application

Provides:
- /api/briefing/* — Generate and retrieve daily market briefings
- /api/chat — Follow-up Q&A with the odds agent
- /api/data/* — Upload, query, and manage odds data
- /health — Health check
"""

import logging
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.briefing import router as briefing_router
from app.api.chat import router as chat_router
from app.api.data import router as data_router

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name}")
    logger.info(f"Model: {settings.model_id}")
    logger.info(f"API key configured: {'yes' if settings.anthropic_api_key else 'NO — set ANTHROPIC_API_KEY'}")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description="AI-powered odds agent for anomaly detection, market analysis, and daily briefings",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiter for LLM endpoints ────────────────────────────────────────────
# Caps total LLM calls (briefing + chat) to prevent runaway API costs in prod.

_RATE_LIMIT_MAX = settings.rate_limit_max
_RATE_LIMIT_WINDOW = settings.rate_limit_window
_rate_log: deque[float] = deque()
_rate_lock = threading.Lock()

_RATE_LIMITED_PATHS = {"/api/briefing/trigger", "/api/chat"}


def _is_rate_limited() -> bool:
    now = time.time()
    with _rate_lock:
        # Purge expired entries
        while _rate_log and _rate_log[0] < now - _RATE_LIMIT_WINDOW:
            _rate_log.popleft()
        if len(_rate_log) >= _RATE_LIMIT_MAX:
            return True
        _rate_log.append(now)
        return False


# Request logging + rate limiting middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()

    # Rate limit LLM-heavy endpoints
    if request.url.path in _RATE_LIMITED_PATHS and request.method == "POST":
        if _is_rate_limited():
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded — max {_RATE_LIMIT_MAX} requests per hour"},
            )

    response = await call_next(request)
    duration = round(time.time() - start, 3)
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration}s)")
    return response


# Register routes
app.include_router(briefing_router)
app.include_router(chat_router)
app.include_router(data_router)


@app.get("/health")
async def health():
    from app.data.store import odds_store
    return {
        "status": "healthy",
        "api_key_configured": bool(settings.anthropic_api_key),
        "model": settings.model_id,
        "data_loaded": len(odds_store.get_games()) > 0,
        "games_count": len(odds_store.get_games()),
    }
