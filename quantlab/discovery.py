"""Deterministic strategy batch discovery; candidate selection never sees holdout.

This implements a real, local research workflow, not AI hypothesis generation.
Use it as an integration target for externally deployed specialist agents.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace

from .market import Bar, Contract, check_bars
from .research import quality_report
from .sim import Settings, simulate


def _digest(bars: list[Bar]) -> str:
    data = [[b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume, b.contract_id]
            for b in bars]
    return hashlib.sha256(json.dumps(data, separators=(",", ":")).encode()).hexdigest()


def batch_discover(bars: list[Bar], contract: Contract, *, synthetic: bool,
                   base: Settings | None = None, lookbacks: tuple[int, ...] = (10, 20, 40),
                   strategies: tuple[str, ...] = ("breakout", "mean_reversion"),
                   min_training_trades: int = 3, max_candidates: int = 25) -> dict:
    """Select ONE best training candidate and check validation; never run final holdout.

    This is not an objective statistically corrected multiple-testing procedure.
    Treat outputs as research triage only, never deployment qualification.
    """
    check_bars(bars, contract)
    if not 1 <= len(lookbacks) * len(strategies) <= max_candidates or max_candidates > 100:
        raise ValueError("Candidate count exceeds bounded research cap")
    if min_training_trades < 1:
        raise ValueError("min_training_trades must be positive")
    base = base or Settings()
    max_lb = max(lookbacks)
    a, b = int(len(bars) * .6), int(len(bars) * .8)
    if min(a, b - a) < max_lb + 3 or len(bars) - b < max_lb + 3:
        raise ValueError("Insufficient observations for reserved final holdout")
    training, validation = bars[:a], bars[a:b]
    candidates = []
    for strategy in strategies:
        if strategy not in ("breakout", "mean_reversion"):
            raise ValueError("Unknown strategy family")
        for lookback in lookbacks:
            cfg = replace(base, strategy=strategy, lookback=lookback)
            result = simulate(training, contract, cfg)
            metrics = result["metrics"]
            # Do NOT maximise Sharpe from intraday bars; the metric is unavailable.
            sufficient = metrics["trade_count"] >= min_training_trades
            score = metrics["net_pnl"] if sufficient and metrics["max_drawdown"] < base.max_drawdown else None
            candidates.append({"name": f"{strategy}-lb{lookback}", "strategy": strategy,
                               "lookback": lookback, "training_metrics": metrics, "score": score,
                               "training_rejected": score is None})
    # Sorting is deterministic. Tie breaker does not peek at validation or holdout.
    eligible = [c for c in candidates if c["score"] is not None]
    eligible.sort(key=lambda c: (-c["score"], c["name"]))
    winner = eligible[0] if eligible else None
    evaluated = None
    if winner:
        cfg = replace(base, strategy=winner["strategy"], lookback=winner["lookback"])
        validation_result = simulate(validation, contract, cfg)
        evaluated = {"name": winner["name"], "settings": asdict(cfg),
                     "metrics": validation_result["metrics"],
                     "risk_events": validation_result["risk_events"],
                     "quality_gate": quality_report(validation_result),
                     "equity_curve": validation_result["equity_curve"],
                     "trades": validation_result["trades"]}
    return {"workflow": "bounded_deterministic_research_batch", "synthetic": synthetic,
            "dataset_sha256": _digest(bars), "contract": asdict(contract), "config": asdict(base),
            "training": {"bars": len(training), "start": training[0].timestamp.isoformat(),
                         "end": training[-1].timestamp.isoformat()},
            "validation": {"bars": len(validation), "start": validation[0].timestamp.isoformat(),
                           "end": validation[-1].timestamp.isoformat()},
            "holdout_reserved": {"bars": len(bars) - b, "start": bars[b].timestamp.isoformat()},
            "candidates": candidates, "selected_candidate": evaluated,
            "candidate_count": len(candidates), "eligible_for_paper": False, "eligible_for_live": False,
            "warnings": ["Rule-based research workflow, not AI-generated alpha",
                         "Multiple comparisons on training data can overfit; selection is not inference",
                         "Validation is not an untouched final holdout",
                         "No independent exchange-level fill validation or market data provenance verification",
                         "A profitable sample cannot establish future profitability"]}
