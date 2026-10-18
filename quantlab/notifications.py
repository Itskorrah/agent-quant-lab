"""Deliberate no-network-by-default notification plan/formatter."""
from __future__ import annotations

import json


def telegram_preview(event: dict) -> str:
    """Prepare text but never send it; deployment requires explicit credentials."""
    allowed = {"research_complete", "validation_failed", "paper_halted", "data_failure"}
    kind = event.get("type")
    if kind not in allowed:
        raise ValueError("Unexpected notification type")
    safe = {k: event.get(k) for k in ("type", "experiment_id", "reason")}
    return "[Agent Quant Lab | simulation/research] " + json.dumps(safe, ensure_ascii=True)
