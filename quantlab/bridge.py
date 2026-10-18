"""Untrusted JSON request adapter for future Hermes agents; no shell/LLM execution."""
from __future__ import annotations

import json
from pathlib import Path

from .orchestration import Queue, ROLES


_ALLOWED_FIELDS = {"role", "request_id", "hypothesis", "dataset_id", "strategy_id", "budget_usd"}


def enqueue_request(queue: Queue, request: dict) -> str:
    if not isinstance(request, dict) or not set(request) <= _ALLOWED_FIELDS:
        raise ValueError("Unexpected agent request fields")
    role = request.get("role")
    rid = request.get("request_id")
    if role not in ROLES or not isinstance(rid, str) or not 1 <= len(rid) <= 128:
        raise ValueError("Role or request ID invalid")
    budget = request.get("budget_usd", 0)
    if type(budget) not in (int, float) or not 0 <= budget <= 5:
        raise ValueError("Request budget exceeds hard cap of $5")
    if role in ("paper_observer", "risk_officer"):
        raise PermissionError("Direct external activation of privileged agents is forbidden")
    for field in ("hypothesis", "dataset_id", "strategy_id"):
        value = request.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 2048):
            raise ValueError("Invalid input field " + field)
    return queue.enqueue(role, request)


def enqueue_json_file(queue: Queue, path: str | Path) -> str:
    """Read a bounded request file; do not execute or interpolate contents."""
    path = Path(path)
    if path.stat().st_size > 8192:
        raise ValueError("Agent request exceeds byte limit")
    return enqueue_request(queue, json.loads(path.read_text(encoding="utf-8")))
