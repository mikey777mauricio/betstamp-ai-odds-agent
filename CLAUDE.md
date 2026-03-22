# Claude Code Instructions

For full codebase documentation, architecture, and conventions, see [AGENTS.md](./AGENTS.md).

## Quick Reference

- **Backend**: `cd backend && uvicorn app.main:app --reload --port 8000`
- **Frontend**: `cd frontend && npm run dev`
- **Tests**: `cd backend && pytest tests/ -v` (82 tests, must all pass)
- **Key principle**: LLM orchestrates, Python computes. All math in `app/tools/`, never in the LLM.
- **Adding tools**: Pure function in `app/tools/` → test in `tests/` → `@tool` wrapper in `app/agent/tools.py`
- **Prompts**: `app/agent/prompts.py` — briefing and chat system prompts
- **Data store**: `app/data/store.py` — in-memory, thread-safe, uploadable via API

