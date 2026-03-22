"""API routes for follow-up chat with the odds agent."""

import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.odds_agent import odds_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(max_length=5000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=50)
    stream: bool = Field(default=True)


@router.post("")
async def chat(request: ChatRequest):
    """
    Send a follow-up question to the odds agent.

    If stream=True (default), returns Server-Sent Events.
    If stream=False, returns the complete response as JSON.
    """
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Convert history to agent format
    history = [{"role": m.role, "content": [{"type": "text", "text": m.content}]} for m in request.history]

    if request.stream:
        return StreamingResponse(
            _stream_response(request.message, history),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = odds_agent.chat(request.message, conversation_history=history)
        return result


async def _stream_response(message: str, history: list[dict]):
    """Generate SSE events from agent streaming response."""
    try:
        async for event in odds_agent.chat_stream(message, conversation_history=history):
            yield f"data: {json.dumps(event)}\n\n"
    except Exception as e:
        logger.error(f"Chat stream error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    finally:
        yield "data: [DONE]\n\n"
