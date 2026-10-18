"""Immutable experiment results and explicit human approval metadata."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Registry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
                        "kind TEXT NOT NULL, status TEXT NOT NULL, sha256 TEXT NOT NULL, report TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS approvals (experiment_id TEXT PRIMARY KEY REFERENCES experiments(id), "
                        "decision TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL, updated_at TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "experiment_id TEXT, timestamp TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL)")
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.db.close()

    def save(self, report: dict, *, kind: str) -> str:
        if kind not in ("synthetic", "historical", "replay", "validation"):
            raise ValueError("Unknown experiment kind")
        payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        identifier = f"EXP-{digest[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            current = self.db.execute("SELECT report FROM experiments WHERE id=?", (identifier,)).fetchone()
            if current:
                if current["report"] != payload:
                    raise RuntimeError("Immutable experiment conflict")
                return identifier
            self.db.execute("INSERT INTO experiments VALUES (?,?,?,?,?,?)",
                            (identifier, now, kind, "recorded", digest, payload))
            self.db.execute("INSERT INTO events (experiment_id,timestamp,action,details) VALUES (?,?,?,?)",
                            (identifier, now, "recorded", kind))
        return identifier

    def get(self, identifier: str) -> dict:
        result = self.db.execute("SELECT report FROM experiments WHERE id=?", (identifier,)).fetchone()
        if result is None:
            raise KeyError(identifier)
        return json.loads(result["report"])

    def list(self) -> list[dict]:
        return [dict(row) for row in self.db.execute(
            "SELECT e.id,e.created_at,e.kind,e.status,a.decision FROM experiments e "
            "LEFT JOIN approvals a ON a.experiment_id=e.id ORDER BY e.created_at DESC")]

    def review(self, identifier: str, *, reviewer: str, decision: str, reason: str) -> None:
        if decision not in ("reject", "reviewed", "approve_replay"):
            raise ValueError("Only rejection, review or offline replay approval supported")
        if not reviewer.strip() or not reason.strip():
            raise ValueError("Reviewer and reason required")
        record = self.db.execute("SELECT kind FROM experiments WHERE id=?", (identifier,)).fetchone()
        if record is None:
            raise KeyError(identifier)
        # NEVER authorise live or externally connected orders from this registry.
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute("INSERT INTO approvals VALUES (?,?,?,?,?) "
                            "ON CONFLICT(experiment_id) DO UPDATE SET decision=excluded.decision, "
                            "reviewer=excluded.reviewer,reason=excluded.reason,updated_at=excluded.updated_at",
                            (identifier, decision, reviewer, reason, now))
            self.db.execute("INSERT INTO events (experiment_id,timestamp,action,details) VALUES (?,?,?,?)",
                            (identifier, now, "review", json.dumps({"reviewer": reviewer, "decision": decision})))
