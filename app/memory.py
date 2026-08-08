"""
Per-session conversation history + in-progress lead field tracking.

Kept in-process (a plain dict) for simplicity, same as the original project's
dev-friendly memory store. For a multi-worker production deployment, swap this
for Redis — the interface below is small enough to reimplement in ~20 lines.
"""
from collections import defaultdict
from typing import Any

MAX_TURNS = 12  # trim history so prompts don't grow unbounded over a long chat

_history: dict[str, list[dict[str, str]]] = defaultdict(list)
_lead_fields: dict[str, dict[str, Any]] = defaultdict(dict)


def get_history(session_id: str) -> list[dict[str, str]]:
    return _history[session_id]


def add_message(session_id: str, role: str, content: str) -> None:
    _history[session_id].append({"role": role, "content": content})
    if len(_history[session_id]) > MAX_TURNS * 2:
        _history[session_id] = _history[session_id][-MAX_TURNS * 2 :]


def get_lead_fields(session_id: str) -> dict[str, Any]:
    return _lead_fields[session_id]


def update_lead_fields(session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge non-empty extracted fields into what we already have for this session."""
    for k, v in updates.items():
        if v not in (None, "", "unknown", "null"):
            _lead_fields[session_id][k] = v
    return _lead_fields[session_id]


def clear_lead_fields(session_id: str) -> None:
    _lead_fields[session_id] = {}
