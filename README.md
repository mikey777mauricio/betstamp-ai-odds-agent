# Betstamp AI Odds Agent

AI-powered odds agent that detects anomalies, analyzes markets, and generates daily briefings across sportsbooks.

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- An Anthropic API key — get one free at [console.anthropic.com](https://console.anthropic.com/)

### 1. Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure your API key (only 1 variable needed)
cp .env.example .env
```

Open `backend/.env` and paste your Anthropic API key:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

That's it — no other configuration required. Start the server:
```bash
uvicorn app.main:app --reload --port 8000
```

Verify it's running:
```bash
curl http://localhost:8000/health
# → {"status":"healthy","api_key_configured":true,"model":"claude-sonnet-4-20250514","data_loaded":true,"games_count":10}
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://localhost:8000` — no `.env` file needed for local development.

### 3. Use It

Open **http://localhost:3000**:
1. Click **Generate Briefing** — watch the live agent trace as it runs
2. Review the structured briefing (anomalies, arbitrage, value plays, rankings)
3. Ask follow-up questions in the chat panel
4. Toggle **Run quality evaluation** to see automated scoring

### Run Tests (no API key needed)

```bash
cd backend
pytest tests/ -v
```

173 tests covering: odds math, anomaly detection (verifies seeded anomalies), market analysis, data store, evaluator scoring, Pydantic validation, edge cases, and thread safety.

### Docker (alternative)

```bash
cp backend/.env.example backend/.env
# Paste your ANTHROPIC_API_KEY in backend/.env
docker compose up --build
```

## Architecture

```
Frontend (Next.js)  →  Backend (FastAPI + Strands SDK)
                         │
                         ├── Structured Briefing Pipeline (deterministic):
                         │     1. DETECT  — stale lines, outliers, arbitrage
                         │     2. ANALYZE — vig, best lines, fair odds, rankings
                         │     3. NARRATE — LLM writes executive summary only
                         │
                         ├── Evaluation Pipeline:
                         │     5 automated metrics scored after each briefing
                         │
                         └── Tools (deterministic Python, 173 tests):
                               math_utils.py     — odds math
                               detection_tools.py — anomaly detection (MAD-based)
                               analysis_tools.py  — market analysis
```

**Key design principle:** The LLM orchestrates, Python computes. All odds math is in deterministic, tested functions. The LLM never does arithmetic — it calls tools and synthesizes results into a narrative. See [DEVLOG.md](./DEVLOG.md) for the full evolution (3 architecture iterations).

## Environment Variables

Only **one** variable is required to run the app:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** | — | Your Anthropic API key ([get one here](https://console.anthropic.com/)) |
| `MODEL_ID` | No | `claude-sonnet-4-20250514` | Claude model to use |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Allowed frontend origin(s) |
| `STALE_THRESHOLD_MINUTES` | No | `120` | Minutes before a line is flagged stale |
| `OUTLIER_Z_THRESHOLD` | No | `2.0` | Z-score threshold for outlier detection |
| `MIN_EDGE_PCT` | No | `1.0` | Minimum edge % for value opportunities |
| `DEBUG` | No | `false` | Enable debug logging |
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` | Backend URL (frontend, only needed if non-default) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/briefing/trigger` | POST | Start briefing generation |
| `/api/briefing/status` | GET | Poll for generation status |
| `/api/briefing/latest` | GET | Get the last generated briefing |
| `/api/briefing/stream` | GET | SSE stream of tool calls during generation |
| `/api/briefing/evaluate` | GET | Quality metrics for the last briefing |
| `/api/chat` | POST | Follow-up Q&A (supports SSE streaming) |
| `/api/data/upload` | POST | Upload new odds data |
| `/api/data/reset` | POST | Reset to sample data |
| `/api/data/games` | GET | List games in dataset |
| `/health` | GET | Health check (includes data status) |

## Deployment

### Backend (Railway)

```bash
railway login
cd backend
railway init
railway variables set ANTHROPIC_API_KEY=sk-ant-your-key-here
railway variables set CORS_ORIGINS=https://your-frontend.vercel.app
railway up
```

### Frontend (Vercel)

```bash
cd frontend
vercel
# Set environment variable: NEXT_PUBLIC_API_URL = your Railway backend URL
vercel --prod
```

## Development Log

See [DEVLOG.md](./DEVLOG.md) for the full development journal — architecture iterations, prompt engineering failures, what AI got wrong, evaluation design, and what I'd improve.
