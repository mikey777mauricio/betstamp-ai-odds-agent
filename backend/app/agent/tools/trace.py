"""
Tool trace infrastructure for briefing and chat modes.

Briefing: shared list (only one briefing runs at a time, SSE polls from different thread)
Chat: per-request list via set_chat_trace() to avoid concurrent request interleaving
"""

import threading
import logging

logger = logging.getLogger(__name__)

# Briefing trace — shared, polled by SSE from a different async context
_briefing_trace: list[dict] = []
_briefing_trace_lock = threading.Lock()

# Chat trace — per-request, set before each chat invocation
_chat_trace_local = threading.local()


def clear_tool_trace():
    """Reset the briefing tool trace."""
    with _briefing_trace_lock:
        _briefing_trace.clear()
    _chat_trace_local.trace = None


def set_chat_trace(trace_list: list[dict]):
    """Set a per-request trace list for chat (avoids concurrent interleaving)."""
    _chat_trace_local.trace = trace_list


def get_tool_trace() -> list[dict]:
    """Get a copy of the current tool trace (briefing or chat)."""
    chat_trace = getattr(_chat_trace_local, "trace", None)
    if chat_trace is not None:
        return list(chat_trace)
    with _briefing_trace_lock:
        return list(_briefing_trace)


def get_tool_trace_since(index: int) -> list[dict]:
    """Get tool calls after given index (used by SSE for briefing)."""
    with _briefing_trace_lock:
        return list(_briefing_trace[index:])


def _log_tool_call(name: str, inputs: dict):
    """Record a tool invocation to the appropriate trace."""
    entry = {"tool": name, "input": inputs}
    # If a chat trace is active, use it; otherwise use the briefing trace
    chat_trace = getattr(_chat_trace_local, "trace", None)
    if chat_trace is not None:
        chat_trace.append(entry)
    else:
        with _briefing_trace_lock:
            _briefing_trace.append(entry)
    logger.info(f"Tool called: {name}({inputs})")
