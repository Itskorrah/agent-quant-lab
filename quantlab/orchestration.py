"""Local deterministic task handoffs; Hermes adapters must call constrained tools.

This module does not claim to start Hermes bots or invoke any LLM provider.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROLES = ("coordinator", "data_steward", "researcher", "developer", "backtest_runner",
         "validator", "risk_officer", "paper_observer", "performance_monitor")
HANDOFFS = {"coordinator": ("data_steward", "researcher"), "data_steward": ("researcher",),
            "researcher": ("developer",), "developer": ("backtest_runner",),
            "backtest_runner": ("validator",), "validator": ("risk_officer",),
            "risk_officer": ("paper_observer",), "paper_observer": ("performance_monitor",),
            "performance_monitor": ("researcher",)}


class Queue:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, role TEXT NOT NULL, "
                        "status TEXT NOT NULL, payload TEXT NOT NULL, result TEXT, updated_at TEXT NOT NULL)")
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.db.close()

    def enqueue(self, role: str, payload: dict) -> str:
        if role not in ROLES or not isinstance(payload, dict):
            raise ValueError("Invalid role or payload")
        identifier = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?)",
                            (identifier, role, "queued", json.dumps(payload, allow_nan=False), None, now))
        return identifier

    def transition(self, identifier: str, *, status: str, result: dict | None = None) -> None:
        allowed = {"queued": {"running", "cancelled"}, "running": {"completed", "failed", "cancelled"},
                   "completed": set(), "failed": set(), "cancelled": set()}
        row = self.db.execute("SELECT status FROM tasks WHERE id=?", (identifier,)).fetchone()
        if not row or status not in allowed[row["status"]]:
            raise ValueError("Illegal task transition")
        with self.db:
            self.db.execute("UPDATE tasks SET status=?, result=?, updated_at=? WHERE id=?",
                            (status, json.dumps(result) if result is not None else None,
                             datetime.now(timezone.utc).isoformat(), identifier))

    def handoff(self, identifier: str, to_role: str, payload: dict) -> str:
        row = self.db.execute("SELECT role,status FROM tasks WHERE id=?", (identifier,)).fetchone()
        if not row or row["status"] != "completed" or to_role not in HANDOFFS[row["role"]]:
            raise PermissionError("Task must complete before an approved role-to-role handoff")
        return self.enqueue(to_role, {"parent_task": identifier, **payload})

    def list(self) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM tasks ORDER BY updated_at DESC")]
