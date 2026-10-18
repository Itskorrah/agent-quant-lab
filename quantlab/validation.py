"""Rolling chronological validation and sensitivity; the holdout remains sealed.

No parameter tuning, strategy selection or statistics are permitted to access the
final untouched 20 percent in this module. Multiple testing remains a blocker.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from .market import Bar, Contract
from .sim import Settings, simulate


def rolling_validation(bars: list[Bar], contract: Contract, settings: Settings, *, folds: int = 3,
                       gap: int = 0) -> dict:
    if folds < 2 or folds > 12 or gap < 0:
        raise ValueError("folds must be 2–12 and gap nonnegative")
    # Reserve final fifth and never simulate it in this function.
    reserved = int(len(bars) * .8)
    available = bars[:reserved]
    min_slice = settings.lookback + 3
    chunk = reserved // (folds + 1)
    if chunk < min_slice or gap >= chunk:
        raise ValueError("Not enough data for rolling folds and gap")
    records = []
    for index in range(folds):
        start = (index + 1) * chunk + gap
        end = (index + 2) * chunk if index < folds - 1 else reserved
        if end - start < min_slice:
            raise ValueError("Validation slice too short after embargo gap")
        subset = available[start:end]
        run = simulate(subset, contract, settings)
        records.append({"fold": index + 1, "start": subset[0].timestamp.isoformat(),
                        "end": subset[-1].timestamp.isoformat(), "training_bars_before_gap": (index + 1) * chunk,
                        "gap_bars": gap, "metrics": run["metrics"], "risk_events": run["risk_events"]})
    return {"settings": asdict(settings), "folds": records,
            "reserved_holdout_start": bars[reserved].timestamp.isoformat(),
            "reserved_holdout_rows": len(bars) - reserved,
            "eligible_for_paper": False,
            "note": "Fold parameters are frozen: no selection logic is executed; excludes final 20%."
                    " Each fold resets positions and indicators; train/validation overlap is not modelled."}


def sensitivity(bars: list[Bar], contract: Contract, settings: Settings,
                *, lookbacks: tuple[int, ...] = (10, 20, 40), extra_cost_ticks: tuple[int, ...] = (0, 2, 4)) -> dict:
    if not lookbacks or not extra_cost_ticks or len(lookbacks) * len(extra_cost_ticks) > 50:
        raise ValueError("Sensitivity matrix must be nonempty and <= 50 combinations")
    if any(v < 2 for v in lookbacks) or any(v < 0 for v in extra_cost_ticks):
        raise ValueError("Invalid sensitivity parameters")
    training_only = bars[:int(.6 * len(bars))]
    runs = []
    for lookback in lookbacks:
        for ticks in extra_cost_ticks:
            cfg = replace(settings, lookback=lookback, slippage_ticks=settings.slippage_ticks + ticks)
            result = simulate(training_only, contract, cfg)
            runs.append({"lookback": lookback, "extra_slippage_ticks": ticks,
                         "net_pnl": result["metrics"]["net_pnl"], "trade_count": result["metrics"]["trade_count"],
                         "max_drawdown": result["metrics"]["max_drawdown"]})
    return {"runs": runs, "sample": "first_60_percent_only", "settings": asdict(settings),
            "multiple_testing_warning": "Do not select a winner from this matrix and then treat it as independent evidence.",
            "eligible_for_paper": False}
