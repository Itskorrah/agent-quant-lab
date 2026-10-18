"""Transparent trade statistics; no invented Sharpe or hidden sampling convention."""
from __future__ import annotations

from statistics import mean, median, stdev


def trade_statistics(trades: list[dict]) -> dict:
    values = [float(t["net_pnl"]) for t in trades]
    winners = [x for x in values if x > 0]
    losers = [-x for x in values if x < 0]
    profit_factor = round(sum(winners) / sum(losers), 4) if losers else None
    return {"count": len(values), "net_pnl": round(sum(values), 2),
            "win_rate": round(len(winners) / len(values), 6) if values else None,
            "mean_trade": round(mean(values), 4) if values else None,
            "median_trade": median(values) if values else None,
            "profit_factor": profit_factor,
            "best_trade": max(values) if values else None,
            "worst_trade": min(values) if values else None,
            "gross_profit": round(sum(winners), 2), "gross_loss": round(sum(losers), 2)}


def utc_daily_statistics(equity_curve: list[dict], *, minimum_days: int = 30) -> dict:
    """Conventional UTC-day series; not a CME RTH-session performance statistic.

    UTC calendar days are not CME trading days. Use this only as an explicitly
    labelled research diagnostic; no implied forward predictiveness.
    """
    days: dict[str, float] = {}
    for point in equity_curve:
        days[point["timestamp"][:10]] = float(point["equity"])
    closes = list(days.values())
    changes = [(b / a - 1) for a, b in zip(closes, closes[1:]) if a > 0]
    if len(changes) < minimum_days or len(changes) < 2:
        return {"utc_days": len(days), "daily_sharpe": None, "reason": "insufficient_utc_days"}
    sd = stdev(changes)
    import math
    return {"utc_days": len(days), "daily_sharpe": round(mean(changes) / sd * math.sqrt(252), 4) if sd > 0 else None,
            "reason": "utc_calendar_day_proxy_not_cme_session", "annualisation_days": 252}
