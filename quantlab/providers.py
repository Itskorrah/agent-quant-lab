"""Cost-gated historical Databento MNQ acquisition.

This optional adapter NEVER fetches billable time series without both a declared
USD cap and an acknowledgement. Always use one raw tradable futures symbol.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .market import Bar, Contract, check_bars, to_csv

RAW_MNQ = re.compile(r"^MNQ[HMUZ]\d{1,2}$")
DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"


def _iso_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Timestamps must include UTC timezone offset")
    return parsed.astimezone(timezone.utc)


def validate_request(symbol: str, start: str, end: str) -> dict:
    if not RAW_MNQ.fullmatch(symbol):
        raise ValueError("Expected a single raw quarterly MNQ contract, e.g. MNQZ6; never MNQ continuous")
    a, b = _iso_utc(start), _iso_utc(end)
    if not a < b:
        raise ValueError("End must follow start")
    if (b - a).days > 31 or (b - a).total_seconds() > 31 * 86400:
        raise ValueError("At most 31 days per request; reduce cost/size and retry")
    return {"dataset": DATASET, "schema": SCHEMA, "symbols": symbol,
            "stype_in": "raw_symbol", "start": a.isoformat(), "end": b.isoformat()}


def _client(client=None):
    if client is not None:
        return client
    if not os.getenv("DATABENTO_API_KEY"):
        raise RuntimeError("DATABENTO_API_KEY missing; create an account and set it outside Git")
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: pip install -e '.[databento]'") from exc
    return db.Historical()


def estimate_cost(symbol: str, start: str, end: str, *, client=None) -> dict:
    spec = validate_request(symbol, start, end)
    estimated = float(_client(client).metadata.get_cost(**spec))
    if not math.isfinite(estimated) or estimated < 0:
        raise ValueError("Vendor returned an invalid cost estimate")
    return {"request": spec, "estimated_usd": estimated,
            "currency": "USD", "estimated_not_final": True,
            "no_time_series_downloaded": True}


def _records(store, symbol: str) -> list[Bar]:
    """Materialise one provider raw-symbol response; fail if unexpected data."""
    df = store.to_df()
    if df.empty:
        raise ValueError("Provider returned no bars")
    allowed = {"open", "high", "low", "close", "volume"}
    if not allowed.issubset(df.columns):
        raise ValueError("Missing OHLCV columns in provider response")
    if "instrument_id" in df.columns and df.instrument_id.nunique() != 1:
        raise ValueError("Provider returned multiple instrument IDs; split by tradable contract")
    if "symbol" in df.columns and set(df.symbol.unique()) != {symbol}:
        raise ValueError("Provider returned unexpected raw symbol")
    times = df["ts_event"] if "ts_event" in df.columns else df.index
    result = []
    for t, row in zip(times, df.to_dict("records"), strict=True):
        dt = t.to_pydatetime() if hasattr(t, "to_pydatetime") else datetime.fromisoformat(str(t))
        if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
            raise ValueError("Vendor timestamps are not explicitly UTC")
        result.append(Bar(dt.astimezone(timezone.utc), float(row["open"]), float(row["high"]),
                          float(row["low"]), float(row["close"]), float(row["volume"]), symbol))
    check_bars(result, Contract(contract_id=symbol), expected_seconds=60)
    return result


def acquire(symbol: str, start: str, end: str, directory: str | Path, *,
            max_usd: float = 0, acknowledge_charges: bool = False, client=None) -> dict:
    """Retrieve data only on explicit acknowledgement and cost estimate <= max_usd.

    Vendor charges can differ from the estimate; the caller must check the vendor's
    billing portal and is responsible for the explicit spending approval.
    """
    if not acknowledge_charges:
        raise PermissionError("Download blocked; specify --acknowledge-data-charges")
    if not math.isfinite(max_usd) or max_usd < 0:
        raise ValueError("Must specify a finite nonnegative --max-usd")
    api = _client(client)
    quote = estimate_cost(symbol, start, end, client=api)
    if quote["estimated_usd"] > max_usd:
        raise PermissionError(f"Cost ${quote['estimated_usd']:.4f} exceeds explicit cap ${max_usd:.4f}")
    dest = Path(directory)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("Output directory already contains data; refusing overwrite/rebill")
    data = api.timeseries.get_range(**quote["request"])
    bars = _records(data, symbol)
    a, b = _iso_utc(start), _iso_utc(end)
    if bars[0].timestamp < a or bars[-1].timestamp >= b:
        raise ValueError("Vendor returned timestamps outside requested range")
    dest.mkdir(parents=True, exist_ok=True)
    raw_path = dest / "vendor_raw.dbn"
    data.to_file(str(raw_path))
    bars_path = dest / "mnq_1m.csv"
    to_csv(bars_path, bars)
    manifest = {
        "provider": "Databento", "dataset": DATASET, "schema": SCHEMA,
        "symbol": symbol, "stype_in": "raw_symbol", "start": a.isoformat(),
        "end": b.isoformat(), "row_count": len(bars),
        "source_kind": "licensed_vendor_purchase_no_redistribution",
        "estimated_charge_usd": quote["estimated_usd"],
        "vendor_raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "normalised_sha256": hashlib.sha256(bars_path.read_bytes()).hexdigest(),
        "bar_timestamp_convention": "start_utc_1m",
        "availability": "Actual vendor entitlements not established by the software",
    }
    (dest / "provenance.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
