"""Point-in-time OHLCV ingestion, instrument identity and integrity checks.

Only known instrument contracts can be backtested; continuous adjusted prices are
not executable prices. CSV timestamps must be offset-aware and start-of-bar UTC.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class Contract:
    symbol: str = "MNQ"
    contract_id: str = "MNQ-DEMO"  # must be replaced for actual data
    multiplier: float = 2.0
    tick_size: float = 0.25
    tick_value: float = 0.5
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not self.contract_id or self.multiplier <= 0 or self.tick_size <= 0:
            raise ValueError("Valid, nonempty contract and positive specifications required")
        if not math.isclose(self.tick_value, self.multiplier * self.tick_size, abs_tol=1e-8):
            raise ValueError("Tick value must equal multiplier times tick size")


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    contract_id: str


def _on_tick(value: float, step: float) -> bool:
    return abs(value / step - round(value / step)) < 1e-7


def check_bars(bars: list[Bar], contract: Contract, *, expected_seconds: int | None = None) -> dict:
    """Fail closed on corrupt data; report rather than fill possible session gaps."""
    if len(bars) < 3:
        raise ValueError("At least three bars required")
    previous = None
    gaps = []
    for i, bar in enumerate(bars):
        if bar.contract_id != contract.contract_id:
            raise ValueError(f"row {i}: contract ID mismatch")
        if bar.timestamp.tzinfo is None or bar.timestamp.utcoffset() is None:
            raise ValueError(f"row {i}: time zone offset missing")
        if bar.timestamp.utcoffset() != timedelta(0):
            raise ValueError(f"row {i}: timestamps must be UTC, not local time")
        if previous is not None:
            delta = (bar.timestamp - previous).total_seconds()
            if delta <= 0:
                raise ValueError(f"row {i}: duplicate or non-increasing timestamp")
            if expected_seconds is not None and delta != expected_seconds:
                gaps.append({"index": i, "seconds": delta, "start": previous.isoformat(), "end": bar.timestamp.isoformat()})
        previous = bar.timestamp
        prices = [bar.open, bar.high, bar.low, bar.close]
        if any(not math.isfinite(p) or p <= 0 for p in prices) or not math.isfinite(bar.volume) or bar.volume < 0:
            raise ValueError(f"row {i}: invalid price or volume")
        if bar.high < max(prices) or bar.low > min(prices):
            raise ValueError(f"row {i}: OHLC inconsistency")
        if not all(_on_tick(p, contract.tick_size) for p in prices):
            raise ValueError(f"row {i}: price violates tick size")
    return {"row_count": len(bars), "first": bars[0].timestamp.isoformat(), "last": bars[-1].timestamp.isoformat(),
            "unexpected_intervals": gaps[:100], "unexpected_interval_count": len(gaps)}


def load_csv(path: str | Path, contract: Contract, *, expected_seconds: int | None = None) -> tuple[list[Bar], dict]:
    """Required fields: timestamp,open,high,low,close,volume,contract_id."""
    path = Path(path)
    bars = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        needed = {"timestamp", "open", "high", "low", "close", "volume", "contract_id"}
        if not reader.fieldnames or not needed.issubset(reader.fieldnames):
            raise ValueError("CSV missing required columns: " + ", ".join(sorted(needed)))
        for i, raw in enumerate(reader):
            try:
                dt = datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
                vals = [float(raw[k]) for k in ("open", "high", "low", "close", "volume")]
                bars.append(Bar(dt, *vals, raw["contract_id"]))
            except (ValueError, TypeError, KeyError) as e:
                raise ValueError(f"row {i + 2}: invalid CSV: {e}") from e
    details = check_bars(bars, contract, expected_seconds=expected_seconds)
    details["file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    details["source"] = str(path)
    details["contract"] = asdict(contract)
    return bars, details


def write_manifest(directory: Path, manifest: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "manifest.json"
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing != manifest:
            raise FileExistsError("Dataset manifest is immutable; use another dataset directory")
    else:
        target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def synthetic_bars(n: int = 500, seed: int = 17, contract: Contract | None = None) -> list[Bar]:
    """Deterministic fabricated prices, rounded to valid ticks. Never real performance evidence."""
    contract = contract or Contract()
    rng = random.Random(seed)
    price = 20000.0
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bars = []
    for i in range(n):
        op = price
        change = rng.randint(-25, 25) * contract.tick_size
        close = max(contract.tick_size, op + change)
        high = max(op, close) + rng.randint(0, 8) * contract.tick_size
        low = min(op, close) - rng.randint(0, 8) * contract.tick_size
        bars.append(Bar(start + timedelta(minutes=i), op, high, low, close, rng.randint(10, 1000), contract.contract_id))
        price = close
    check_bars(bars, contract, expected_seconds=60)
    return bars


def to_csv(path: Path, bars: list[Bar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "contract_id"])
        for b in bars:
            writer.writerow([b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume, b.contract_id])
