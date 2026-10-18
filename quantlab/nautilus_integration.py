"""Experimental NautilusTrader 2.x MNQ engine entry point.

Optional dependency. This runner requires a *single raw contract* and 1-minute
start-stamped UTC bars. It is not a production-quality strategy validation tool;
fill modelling, fees, exchange sessions and futures roll are incomplete.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .market import Contract, load_csv

RAW_MNQ = re.compile(r"^MNQ[HMUZ]\d{1,2}$")


def _ns(dt: datetime) -> int:
    if dt.tzinfo is None:
        raise ValueError("UTC aware timestamp required")
    return int(dt.timestamp() * 1_000_000_000)


def convert_bars(bars, symbol: str, factory=None) -> list:
    """Build Nautilus bars only after full input integrity checking.

    Injection of factory allows tests to verify timestamp conversion without the
    Rust wheel. The real default factory is NautilusTrader's model types.
    """
    from .market import check_bars
    check_bars(bars, Contract(contract_id=symbol))
    if factory is None:
        from nautilus_trader.model import Bar, BarType, Price, Quantity
        bar_type = BarType.from_str(f"{symbol}.SIM-1-MINUTE-LAST-EXTERNAL")
        def factory(b, event, init):
            return Bar(bar_type=bar_type, open=Price(b.open, precision=2),
                       high=Price(b.high, precision=2), low=Price(b.low, precision=2),
                       close=Price(b.close, precision=2),
                       volume=Quantity.from_int(int(b.volume)),
                       ts_event=event, ts_init=init)
    out = []
    for b in bars:
        if b.volume < 0 or int(b.volume) != b.volume:
            raise ValueError("CME one-minute traded volume must be a whole number")
        event_ns = _ns(b.timestamp)
        out.append(factory(b, event_ns, event_ns + 60_000_000_000))
    return out


def run_nautilus(csv: str | Path, raw_contract: str, *,
                 out: str | Path, starting_cash: float = 20_000.0) -> dict:
    if not RAW_MNQ.fullmatch(raw_contract):
        raise ValueError("Require raw MNQ quarterly contract, not continuous series")
    if starting_cash <= 0:
        raise ValueError("starting_cash must be positive")
    bars, provenance = load_csv(csv, Contract(contract_id=raw_contract))
    try:
        import nautilus_trader
        from nautilus_trader.backtest import BacktestEngine
        from nautilus_trader.common import LogLevel
        from nautilus_trader.config import BacktestEngineConfig, LoggerConfig, StrategyConfig
        from nautilus_trader.execution import MakerTakerFeeModel
        from nautilus_trader.indicators import ExponentialMovingAverage
        from nautilus_trader.model import (AccountType, AssetClass, BarType, Currency,
                                          FuturesContract, InstrumentId, Money, OmsType,
                                          OrderSide, Price, Quantity, Symbol, Venue)
        from nautilus_trader.trading import Strategy
    except ImportError as exc:
        raise RuntimeError("NautilusTrader is not installed. Use Python 3.13+ and pip install -U --pre nautilus_trader") from exc
    if not nautilus_trader.__version__.startswith("2."):
        raise RuntimeError(f"NautilusTrader 2.x required, found {nautilus_trader.__version__}")

    class CrossConfig(StrategyConfig):
        def __init__(self, *, instrument_id, bar_type, **kwargs):
            super().__init__()
            self.instrument_id = instrument_id
            self.bar_type = bar_type

    class Cross(Strategy):
        def __init__(self, config):
            super().__init__(config)
            self.fast = ExponentialMovingAverage(10)
            self.slow = ExponentialMovingAverage(20)

        def on_start(self):
            self.register_indicator_for_bars(self.config.bar_type, self.fast)
            self.register_indicator_for_bars(self.config.bar_type, self.slow)
            self.subscribe_bars(self.config.bar_type)

        def on_bar(self, _bar):
            if not self.indicators_initialized():
                return
            # Demonstration only: 1 contract max, simple EMA cross (not a validated strategy).
            iid = self.config.instrument_id
            if self.fast.value > self.slow.value and self.portfolio.is_net_flat(iid):
                self._enter(OrderSide.BUY)
            elif self.fast.value < self.slow.value and self.portfolio.is_net_flat(iid):
                self._enter(OrderSide.SELL)
            elif self.fast.value > self.slow.value and self.portfolio.is_net_short(iid):
                self.close_all_positions(iid)
            elif self.fast.value < self.slow.value and self.portfolio.is_net_long(iid):
                self.close_all_positions(iid)

        def _enter(self, side):
            iid = self.config.instrument_id
            instrument = self.cache.instrument(iid)
            order = self.order_factory.market(iid, side, instrument.make_qty(Decimal(1)))
            self.submit_order(order)

        def on_stop(self):
            self.close_all_positions(self.config.instrument_id)

    sim_venue = Venue("SIM")
    instrument_id = InstrumentId.from_str(f"{raw_contract}.SIM")
    # Contract activation/expiry placeholders intentionally require user input
    # before using this for multi-month or expiry-adjacent research.
    start_ns = _ns(bars[0].timestamp)
    last_ns = _ns(bars[-1].timestamp) + 60_000_000_000
    instrument = FuturesContract(
        instrument_id=instrument_id, raw_symbol=Symbol(raw_contract),
        asset_class=AssetClass.INDEX, exchange="XCME", underlying="MNQ",
        activation_ns=start_ns, expiration_ns=last_ns + 86_400_000_000_000,
        currency=Currency.from_str("USD"), price_precision=2,
        price_increment=Price.from_str("0.25"), size_increment=Quantity.from_int(1),
        size_precision=0, multiplier=Quantity.from_int(2), lot_size=Quantity.from_int(1),
        ts_event=0, ts_init=0, margin_init=Decimal("0.1"), margin_maint=Decimal("0.1"),
    )
    bar_type = BarType.from_str(f"{raw_contract}.SIM-1-MINUTE-LAST-EXTERNAL")
    engine = BacktestEngine(config=BacktestEngineConfig(logging=LoggerConfig(stdout_level=LogLevel.ERROR)))
    try:
        engine.add_venue(
            venue=sim_venue, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
            base_currency=Currency.from_str("USD"),
            starting_balances=[Money(starting_cash, Currency.from_str("USD"))],
            default_leverage=Decimal(1), bar_execution=True,
            fee_model=MakerTakerFeeModel(maker_rate=Decimal(0), taker_rate=Decimal(0)),
        )
        engine.add_instrument(instrument)
        engine.add_data(convert_bars(bars, raw_contract))
        engine.add_strategy(Cross(CrossConfig(instrument_id=instrument_id, bar_type=bar_type)))
        engine.run()
        fills = engine.generate_order_fills_report()
        positions = engine.generate_positions_report()
        account = engine.generate_account_report(venue=sim_venue)
        result = {
            "engine": "NautilusTrader", "version": nautilus_trader.__version__,
            "status": "experimental_unverified_external_wheel",
            "dataset": provenance, "bar_count": len(bars),
            "fills": json.loads(fills.to_json(orient="records", date_format="iso")),
            "positions": json.loads(positions.to_json(orient="records", date_format="iso")),
            "account": json.loads(account.to_json(orient="records", date_format="iso")),
            "warnings": [
                "This engine is a first-run integration, not validated financial accounting",
                "Fees and slippage are zero here; DO NOT use performance to screen trading strategies",
                "Activation and expiry are placeholders, not verified exchange contract metadata",
                "CME trading sessions, rolls, exchange margin and order fill fidelity are NOT validated",
                "Only a single raw contract supported; bar-order assumptions need independent test",
            ], "live_trading": False,
        }
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")
        return result
    finally:
        engine.dispose()
