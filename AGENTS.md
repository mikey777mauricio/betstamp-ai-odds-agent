# Agents Guide — Betstamp AI Odds Agent

This document helps AI coding agents (Claude Code, Copilot, Cursor, etc.) understand and work with this codebase effectively.

## Project Overview

An AI-powered odds analysis agent that ingests sportsbook odds data and produces:
1. **Anomaly detection** — stale lines, outlier prices, arbitrage opportunities
2. **Market analysis** — vig calculations, best lines, fair odds, sportsbook rankings
3. **Daily briefings** — structured reports a human analyst can act on
4. **Follow-up chat** — grounded Q&A about the analysis

## Architecture

```
bet-stamp/
├── backend/          Python FastAPI + Strands SDK (Claude agent)
│   ├── app/
│   │   ├── main.py           FastAPI app entry point
│   │   ├── config.py         Pydantic settings (env vars)
│   │   ├── agent/            LLM agent layer
│   │   │   ├── odds_agent.py   Agent orchestrator (briefing + chat + streaming)
│   │   │   ├── prompts.py      System prompts (briefing, narrative, chat)
│   │   │   └── tools/          @tool decorated wrappers (package)
│   │   │       ├── __init__.py     Exports ALL_TOOLS, BRIEFING_TOOLS, CHAT_TOOLS
│   │   │       ├── trace.py        Tool call tracing (shared + per-request)
│   │   │       ├── data_tools.py   get_games, get_odds_for_game, get_market_summary
│   │   │       ├── detection_tools.py  run_detection, detect_stale/outlier/arb
│   │   │       ├── analysis_tools.py   run_analysis, vig, best lines, rankings, value
│   │   │       └── math_tools.py       implied prob, vig calc, fair odds, arb check
│   │   ├── models/
│   │   │   └── briefing.py     Pydantic models (StructuredBriefing, alerts, rankings)
│   │   ├── eval/
│   │   │   └── evaluator.py    Briefing quality scorer (completeness, recall, etc.)
│   │   ├── tools/            Deterministic computation (NO LLM)
│   │   │   ├── math_utils.py    Odds math (implied prob, vig, fair odds, arb)
│   │   │   ├── detection_tools.py  Anomaly detection (stale, outlier, arb)
│   │   │   └── analysis_tools.py   Market analysis (vig, best lines, rankings)
│   │   ├── api/              HTTP endpoints
│   │   │   ├── briefing.py     POST trigger + GET status/latest/evaluate
│   │   │   ├── chat.py         POST with SSE streaming
│   │   │   └── data.py         Upload, reset, query odds data
│   │   └── data/
│   │       ├── store.py         Thread-safe in-memory data store
│   │       └── sample_odds_data.json
│   └── tests/                152 tests passing, all deterministic
│       ├── test_math.py        Odds formula verification (34 tests)
│       ├── test_detection.py   Anomaly detection with seeded anomalies (29 tests)
│       ├── test_analysis.py    Vig, best lines, rankings (20 tests)
│       ├── test_data_store.py  Data CRUD operations (10 tests)
│       ├── test_eval.py        Evaluator scoring + structured eval (22 tests)
│       ├── test_models.py      Pydantic model validation + clamping (14 tests)
│       ├── test_edge_cases.py  Math edge cases, thread safety (23 tests)
│       └── test_api.py         API integration tests (17 tests, requires SDK)
├── frontend/         Next.js 16 + TypeScript + Tailwind 4
│   └── src/
│       ├── app/
│       │   ├── page.tsx         Main page (idle/generating/ready states + SSE)
│       │   ├── layout.tsx       Root layout with meta tags
│       │   └── error.tsx        React Error Boundary
│       ├── components/
│       │   ├── BriefingDisplay.tsx   Structured briefing cards + glossary tooltips
│       │   ├── ChatInterface.tsx     Follow-up chat with streaming + tool trace
│       │   └── ToolCallTrace.tsx     Expandable tool call display
│       └── lib/
│           ├── api.ts           Backend API client + TypeScript interfaces
│           └── tools.ts         Shared tool labels, stages, colors
├── DEVLOG.md         Development log (weighted heavily in evaluation)
├── AGENTS.md         This file — AI agent coding guide
├── CLAUDE.md         Claude Code instructions
└── README.md         Setup instructions
```

## Key Design Principle

**The LLM orchestrates; Python computes.** All odds math lives in `app/tools/` as pure, tested functions. The Strands `@tool` wrappers in `app/agent/tools/` expose them to the LLM. The agent never does arithmetic — it calls tools and synthesizes results.

## Structured Output Architecture

The briefing pipeline uses **deterministic tools → Pydantic models → LLM narrative only**:
1. Tools run directly (no LLM) to produce structured data
2. Results are validated through Pydantic models with field validators
3. The LLM writes only the executive summary narrative
4. Frontend renders structured data in dedicated React components

## Working With This Codebase

### Running Tests
```bash
cd backend
pytest tests/ -v          # All 152 tests
pytest tests/test_math.py # Just math verification
```

### Starting Locally
```bash
# Backend (requires ANTHROPIC_API_KEY in backend/.env for agent features)
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev
```

### Common Tasks

**Adding a new odds calculation:**
1. Add the pure function to `backend/app/tools/math_utils.py`
2. Add tests in `backend/tests/test_math.py`
3. If the agent needs it, add a `@tool` wrapper in `backend/app/agent/tools/math_tools.py`
4. Add it to the appropriate tool list in `backend/app/agent/tools/__init__.py`

**Adding a new detection type:**
1. Add the detection function to `backend/app/tools/detection_tools.py`
2. Add tests in `backend/tests/test_detection.py`
3. Wire it into `run_all_detection()` so the briefing picks it up
4. Optionally add a `@tool` wrapper in `backend/app/agent/tools/detection_tools.py`

**Modifying the briefing structure:**
1. Update Pydantic models in `backend/app/models/briefing.py`
2. Edit the narrative prompt in `backend/app/agent/prompts.py`
3. Update the structured briefing builder in `backend/app/agent/odds_agent.py`

**Adding a new API endpoint:**
1. Create route in `backend/app/api/`
2. Register in `backend/app/main.py` with `app.include_router()`

### Data Schema

Each odds record has this shape:
```json
{
  "game_id": "nba_20260320_lal_bos",
  "sport": "NBA",
  "home_team": "Boston Celtics",
  "away_team": "Los Angeles Lakers",
  "commence_time": "2026-03-20T00:10:00Z",
  "sportsbook": "DraftKings",
  "markets": {
    "spread": { "home_line": -5.5, "home_odds": -111, "away_line": 5.5, "away_odds": -111 },
    "moneyline": { "home_odds": -228, "away_odds": 196 },
    "total": { "line": 220.0, "over_odds": -115, "under_odds": -116 }
  },
  "last_updated": "2026-03-19T18:04:00Z"
}
```

### Known Seeded Anomalies in Sample Data

The sample data has intentional anomalies the detection tools must catch:
- **Stale**: PointsBet LAL/BOS (09:15), Caesars ATL/CHA (08:00), BetRivers DAL/PHX (11:30)
- **Outlier**: BetMGM MIL/DEN moneyline (-195 vs ~-130), Caesars POR/UTA total (223.5 vs ~217)
- **Arbitrage**: Check across books for combined implied < 100%

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes (for agent) | — | Anthropic API key |
| `MODEL_ID` | No | `claude-sonnet-4-20250514` | Claude model to use |
| `MAX_TOKENS` | No | `8192` | Max tokens per response |
| `STALE_THRESHOLD_MINUTES` | No | `120` | Minutes behind to flag stale |
| `OUTLIER_Z_THRESHOLD` | No | `2.0` | Z-score for outlier detection |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Allowed CORS origins (comma-separated) |

### Dependencies

**Backend**: FastAPI, Pydantic, Strands Agents SDK, Anthropic, SSE-Starlette
**Frontend**: Next.js 16, React 19, Tailwind CSS 4, TypeScript

### Code Style
- Python: ruff (line-length 100)
- TypeScript: ESLint (Next.js defaults)
- No unnecessary abstractions — keep it simple
- Every math function must have a corresponding test
- Tool docstrings matter — the LLM reads them to decide which tool to call
