"""Conservative, deterministic, bar-open simulated trading for research/replay.

No broker imports, sockets, credentials or live-order methods. This is explicitly
NOT a substitute for tick-accurate, exchange-aware production simulation.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import mean, stdev

from .market import Bar, Contract, check_bars


@dataclass(frozen=True)
class Settings:
    starting_cash: float = 20000.0
    fee_per_side: float = 1.5
    slippage_ticks: int = 2
    lookback: int = 20
    max_contracts: int = 1
    max_daily_loss: float = 250.0
    max_drawdown: float = 0.15
    margin_per_contract: float = 2000.0  # illustration only, not an exchange margin quote
    strategy: str = "breakout"  # breakout | mean_reversion

    def __post_init__(self) -> None:
        if (self.starting_cash <= 0 or self.fee_per_side < 0 or self.slippage_ticks < 0
                or self.lookback < 2 or self.max_contracts != 1 or self.max_daily_loss <= 0
                or not 0 < self.max_drawdown < 1 or self.margin_per_contract <= 0
                or self.strategy not in ("breakout", "mean_reversion")):
            raise ValueError("Invalid simulation settings; only 1 contract supported")


def signal(bars: list[Bar], last_completed: int, lookback: int, strategy: str) -> int:
    """Decision uses only bars <= last_completed. Outputs -1, 0 or +1."""
    previous = bars[last_completed - lookback:last_completed]
    if len(previous) != lookback:
        return 0
    price = bars[last_completed].close
    hi = max(b.high for b in previous)
    lo = min(b.low for b in previous)
    if strategy == "breakout":
        return 1 if price > hi else (-1 if price < lo else 0)
    if strategy == "mean_reversion":
        return -1 if price > hi else (1 if price < lo else 0)
    raise ValueError("Unknown strategy")


def _round_to_tick(price: float, tick: float, side: int) -> float:
    # Adverse rounding in direction of execution: buy rounds upward; sell downward.
    units = price / tick
    return round((math.ceil(units - 1e-9) if side > 0 else math.floor(units + 1e-9)) * tick, 8)


def simulate(bars: list[Bar], contract: Contract, cfg: Settings) -> dict:
    check_bars(bars, contract)
    if len(bars) < cfg.lookback + 3:
        raise ValueError("Insufficient bars to evaluate signals")
    cash = cfg.starting_cash
    pos = 0
    entry = 0.0
    entry_fee = 0.0
    entry_time = ""
    trades: list[dict] = []
    fills: list[dict] = []
    equity: list[dict] = []
    peak = cash
    max_dd = 0.0
    day = None
    day_start = cash
    blocked = False
    permanently_halted = False
    blockers: set[str] = set()

    def fill(side: int, base_price: float, bar: Bar, reason: str) -> float:
        nonlocal cash
        px = _round_to_tick(base_price + side * cfg.slippage_ticks * contract.tick_size,
                            contract.tick_size, side)
        cash -= cfg.fee_per_side
        fills.append({"timestamp": bar.timestamp.isoformat(), "action": "buy" if side == 1 else "sell",
                      "price": px, "quantity": 1, "fee": cfg.fee_per_side, "reason": reason})
        return px

    def close(bar: Bar, base: float, reason: str) -> None:
        nonlocal pos, cash, entry, entry_fee
        if not pos:
            return
        exit_px = fill(-pos, base, bar, reason)
        gross = (exit_px - entry) * pos * contract.multiplier
        cash += gross
        trades.append({"entry": entry_time, "exit": bar.timestamp.isoformat(), "side": "long" if pos == 1 else "short",
                       "entry_price": entry, "exit_price": exit_px, "gross_pnl": round(gross, 2),
                       "net_pnl": round(gross - entry_fee - cfg.fee_per_side, 2), "reason": reason})
        pos = 0
        entry = 0.0
        entry_fee = 0.0

    for i, bar in enumerate(bars):
        if bar.timestamp.date() != day:
            day = bar.timestamp.date()
            day_start = cash + ((bar.open - entry) * pos * contract.multiplier if pos else 0)
            blocked = permanently_halted  # daily guard resets; total drawdown does not
        if i > cfg.lookback:
            target = signal(bars, i - 1, cfg.lookback, cfg.strategy)
            if pos and target != pos:
                close(bar, bar.open, "signal_exit")
            # No same-bar reversal. Flat-to-position is allowed only if flat at
            # start of decision (prevents reversal from optimistic double-fill).
            if pos == 0 and target and not blocked and (not fills or fills[-1]["timestamp"] != bar.timestamp.isoformat()):
                if cash >= cfg.margin_per_contract + cfg.fee_per_side:
                    entry = fill(target, bar.open, bar, "signal_entry")
                    pos = target
                    entry_time = bar.timestamp.isoformat()
                    entry_fee = cfg.fee_per_side
                else:
                    blockers.add("illustrative_margin_insufficient")
        mark = cash + ((bar.close - entry) * pos * contract.multiplier if pos else 0)
        peak = max(peak, mark)
        dd = (peak - mark) / peak if peak > 0 else 1.0
        max_dd = max(dd, max_dd)
        if mark <= day_start - cfg.max_daily_loss:
            blocked = True
            blockers.add("daily_loss_limit")
        if dd >= cfg.max_drawdown:
            permanently_halted = True
            blocked = True
            blockers.add("total_drawdown_limit")
        if blocked and pos:
            # Conservative same-bar-close emergency liquidation is an *assumption*.
            close(bar, bar.close, "risk_halt")
            mark = cash
        equity.append({"timestamp": bar.timestamp.isoformat(), "equity": round(mark, 2)})
    if pos:
        close(bars[-1], bars[-1].close, "end_of_data")
        equity[-1]["equity"] = round(cash, 2)
    # Intraday returns are deliberately NOT annualised using daily sqrt(252).
    returns = [(equity[i]["equity"] - equity[i - 1]["equity"]) / equity[i - 1]["equity"]
               for i in range(1, len(equity)) if equity[i - 1]["equity"] > 0]
    # Avoid a pretend Sharpe: timing/session schedule is not established.
    wins = sum(1 for t in trades if t["net_pnl"] > 0)
    return {"contract": asdict(contract), "settings": asdict(cfg), "bar_count": len(bars),
            "trades": trades, "fills": fills, "equity_curve": equity,
            "metrics": {"ending_equity": round(cash, 2), "net_pnl": round(cash - cfg.starting_cash, 2),
                        "trade_count": len(trades), "win_rate": wins / len(trades) if trades else None,
                        "max_drawdown": round(max_dd, 6), "sharpe": None},
            "risk_events": sorted(blockers), "synthetic_or_historical": "caller_must_label",
            "warnings": ["Research/replay simulation only; fills are modelled, not observed",
                         "Intrabar risk liquidation is assumed at bar close, potentially optimistic in gaps",
                         "Daily loss follows UTC date, not CME trading session",
                         "Bar-based simulation does not model order book, expiry, roll or intrabar path",
                         "Sharpe intentionally unavailable for intraday bars"]}
