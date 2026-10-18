"""Tamper-evident append-only offline replay log with restart verification.

This is an audit replay of already-simulated events, not a live paper broker.
A hash chain does not stop a privileged user editing/replacing the whole file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _hash(prev: str, payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256((prev + "\n" + blob).encode()).hexdigest()


def verify(path: str | Path) -> dict:
    path = Path(path)
    prev = "0" * 64
    count = 0
    if not path.exists():
        return {"verified": True, "events": 0, "tip": prev}
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Journal corrupted on line {lineno}") from exc
            if (event.get("seq") != lineno or event.get("previous_hash") != prev
                    or event.get("hash") != _hash(prev, event.get("payload"))):
                raise ValueError(f"Journal failed hash validation on line {lineno}")
            prev = event["hash"]
            count += 1
    return {"verified": True, "events": count, "tip": prev}


def append(path: str | Path, payload: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = verify(path)  # fail closed: never append after broken chain
    record = {"seq": state["events"] + 1, "previous_hash": state["tip"], "payload": payload,
              "hash": _hash(state["tip"], payload)}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        f.flush()
        import os
        os.fsync(f.fileno())
    return record


def record_replay(path: str | Path, run: dict) -> dict:
    """Create a verified, immutable hash-chain audit in one bounded write."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    events = ([{"type": "start", "contract": run["contract"], "settings": run["settings"], "bar_count": run["bar_count"]}]
              + [{"type": "fill", **fill} for fill in run["fills"]]
              + [{"type": "finish", "metrics": run["metrics"], "risk_events": run["risk_events"]}])
    previous = "0" * 64
    # Exclusive creation preserves previous evidence even if a run is repeated.
    with path.open("x", encoding="utf-8") as stream:
        for number, payload in enumerate(events, 1):
            digest = _hash(previous, payload)
            record = {"seq": number, "previous_hash": previous, "payload": payload, "hash": digest}
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
            previous = digest
        stream.flush()
        import os
        os.fsync(stream.fileno())
    return verify(path)
