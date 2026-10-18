"""Chronological evaluation and evidence-backed research gates (not proof of edge)."""
from __future__ import annotations

from dataclasses import asdict

from .market import Bar, Contract
from .sim import Settings, simulate


def experiment(bars: list[Bar], contract: Contract, settings: Settings, *, synthetic: bool) -> dict:
    """Avoid peeking at a holdout during tuning: return holdout only when frozen=True."""
    n = len(bars)
    if n < 3 * (settings.lookback + 3):
        raise ValueError("Not enough observations for three independent partitions")
    a, b = int(n * 0.6), int(n * 0.8)
    if min(a, b - a, n - b) < settings.lookback + 3:
        raise ValueError("Each partition must include sufficient warmup")
    sections = {"development": bars[:a], "validation": bars[a:b]}
    runs = {name: simulate(chunk, contract, settings) for name, chunk in sections.items()}
    return {"synthetic": synthetic, "contract": asdict(contract), "settings": asdict(settings),
            "partitions": {name: {"start": items[0].timestamp.isoformat(),
                                  "end": items[-1].timestamp.isoformat(), "bars": len(items)}
                           for name, items in sections.items()},
            "holdout_reserved": {"rows": n - b, "start": bars[b].timestamp.isoformat()},
            "development": runs["development"], "validation": runs["validation"],
            "eligible_for_paper": False, "eligible_for_live": False,
            "warnings": ["Holdout not evaluated in initial research; freeze settings before final evaluation",
                         "Small repeated experiments are vulnerable to multiple-comparison bias",
                         "Backtest results alone never authorise paper or live trading"]}


def final_holdout(bars: list[Bar], contract: Contract, settings: Settings, *, frozen: bool,
                  synthetic: bool) -> dict:
    if not frozen:
        raise PermissionError("Freeze strategy parameters and record development results before holdout")
    if synthetic:
        raise PermissionError("Synthetic data cannot qualify for final investment validation")
    a = int(len(bars) * 0.8)
    result = simulate(bars[a:], contract, settings)
    return {"evaluation": "single-use-final-holdout", "result": result,
            "warning": "Holdout access must be recorded outside this tool; repeated access invalidates it",
            "eligible_for_paper": False, "eligible_for_live": False}


def quality_report(run: dict, min_trades: int = 30, max_drawdown: float = 0.15) -> dict:
    m = run["metrics"]
    tests = {"trades_sufficient": m["trade_count"] >= min_trades,
             "drawdown_within_limit": m["max_drawdown"] <= max_drawdown,
             "net_after_costs_positive": m["net_pnl"] > 0,
             "execution_model_independently_verified": False,
             "holdout_unseen_and_validated": False,
             "paper_forward_evidence": False}
    return {"checks": tests, "all_pass": all(tests.values()),
            "decision": "review_only" if any(tests.values()) else "reject_or_inconclusive",
            "note": "Missing evidence is not an automatic pass. Metrics alone cannot validate a trading edge."}
