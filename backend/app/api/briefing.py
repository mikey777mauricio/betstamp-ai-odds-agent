"""API routes for briefing generation and retrieval."""

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.odds_agent import odds_agent
from app.agent.tools import get_tool_trace_since
from app.eval.evaluator import BriefingEvaluator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/briefing", tags=["briefing"])


class BriefingStatus(BaseModel):
    status: str  # "idle", "generating", "ready", "error"
    briefing: dict | None = None
    error: str | None = None


# Thread-safe state tracking
_state_lock = threading.Lock()
_state = {"status": "idle", "error": None, "last_trigger": None}

TRIGGER_COOLDOWN_SECONDS = 15


GENERATION_TIMEOUT_SECONDS = 300  # 5 minute max


def _generate_in_background():
    """Run briefing generation in background task with timeout."""
    with _state_lock:
        _state["status"] = "generating"
        _state["error"] = None

    result = [None]
    error = [None]

    def _run():
        try:
            result[0] = odds_agent.generate_structured_briefing()
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join(timeout=GENERATION_TIMEOUT_SECONDS)

    if thread.is_alive():
        logger.error("Briefing generation timed out")
        with _state_lock:
            _state["status"] = "error"
            _state["error"] = f"Generation timed out after {GENERATION_TIMEOUT_SECONDS}s"
        return

    if error[0]:
        logger.error(f"Briefing generation failed: {error[0]}", exc_info=True)
        with _state_lock:
            _state["status"] = "error"
            _state["error"] = str(error[0])
    else:
        with _state_lock:
            _state["status"] = "ready"
        logger.info("Briefing generated successfully")


@router.post("/trigger")
async def trigger_briefing(background_tasks: BackgroundTasks):
    """Trigger briefing generation. Returns immediately; poll /status for result."""
    with _state_lock:
        if _state["status"] == "generating":
            return {"message": "Briefing generation already in progress", "status": "generating"}

        # Rate limit
        last = _state.get("last_trigger")
        if last:
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < TRIGGER_COOLDOWN_SECONDS:
                remaining = int(TRIGGER_COOLDOWN_SECONDS - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail=f"Please wait {remaining}s before triggering again",
                )

        _state["last_trigger"] = datetime.now(timezone.utc)

    background_tasks.add_task(_generate_in_background)
    return {"message": "Briefing generation started", "status": "generating"}


@router.get("/status")
async def get_status() -> BriefingStatus:
    """Check briefing generation status. Returns the briefing when ready."""
    with _state_lock:
        status = _state["status"]
        error = _state.get("error")
    briefing = odds_agent.last_briefing if status == "ready" else None
    return BriefingStatus(status=status, briefing=briefing, error=error)


@router.get("/stream")
async def stream_progress():
    """SSE stream of tool calls as they happen during briefing generation."""

    async def event_generator():
        seen = 0
        while True:
            new_calls = get_tool_trace_since(seen)
            for call in new_calls:
                data = json.dumps({"type": "tool_call", "tool": call["tool"], "input": call["input"]})
                yield f"data: {data}\n\n"
                seen += 1

            with _state_lock:
                status = _state["status"]
                error = _state.get("error")

            if status == "ready":
                yield f"data: {json.dumps({'type': 'done', 'status': 'ready'})}\n\n"
                break
            elif status == "error":
                yield f"data: {json.dumps({'type': 'done', 'status': 'error', 'error': error or ''})}\n\n"
                break
            elif status == "idle":
                yield f"data: {json.dumps({'type': 'done', 'status': 'idle'})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/evaluate")
async def evaluate_briefing():
    """Evaluate the most recently generated briefing on quality metrics."""
    briefing = odds_agent.last_briefing
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing has been generated yet")

    evaluator = BriefingEvaluator()
    briefing_text = briefing.get("narrative") or briefing.get("briefing", "")

    # Pass structured data for enhanced evaluation
    is_structured = "overview" in briefing
    scores = evaluator.evaluate(
        briefing_text,
        briefing["tool_calls"],
        structured_data=briefing if is_structured else None,
    )

    return {
        "generated_at": briefing.get("generated_at"),
        "duration_seconds": briefing.get("duration_seconds"),
        "scores": scores,
        "quality_metrics": briefing.get("quality_metrics"),
    }


@router.get("/latest")
async def get_latest_briefing():
    """Get the most recently generated briefing."""
    briefing = odds_agent.last_briefing
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing has been generated yet")
    return briefing
