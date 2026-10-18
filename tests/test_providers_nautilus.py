"""Network-free verification of strict cost gating and bar timestamp semantics."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock


class FakeSeries:
    def __init__(self, values):
        self.values = values

    def nunique(self):
        return len(set(self.values))


class FakeFrame:
    def __init__(self, rows, times):
        self._rows = rows
        self.index = times
        self.columns = list(rows[0])
        self.empty = not bool(rows)

    def __getattr__(self, field):
        if field in self.columns:
            return FakeSeries([r[field] for r in self._rows])
        raise AttributeError(field)

    def to_dict(self, orientation):
        assert orientation == "records"
        return self._rows


from quantlab.market import Contract, synthetic_bars
from quantlab.nautilus_integration import convert_bars, run_nautilus
from quantlab.providers import acquire, estimate_cost, validate_request, _records


class TestDataAcquisition(unittest.TestCase):
    START = "2026-10-01T00:00:00+00:00"
    END = "2026-10-02T00:00:00+00:00"

    def test_raw_contract_only(self):
        self.assertEqual(validate_request("MNQZ6", self.START, self.END)["symbols"], "MNQZ6")
        for bad in ("MNQ", "MNQ.c.0", "NQZ6", "MNQZ6;ALL_SYMBOLS", "MNQH2026", "MNQZ6,MNQH7"):
            with self.subTest(symbol=bad), self.assertRaises(ValueError):
                validate_request(bad, self.START, self.END)

    def test_invalid_dates(self):
        with self.assertRaises(ValueError):
            validate_request("MNQZ6", "2026-10-01", self.END)
        with self.assertRaises(ValueError):
            validate_request("MNQZ6", self.END, self.START)
        with self.assertRaises(ValueError):
            validate_request("MNQZ6", self.START, "2026-12-01T00:00:00Z")

    def test_quote_uses_metadata_only(self):
        client = MagicMock()
        client.metadata.get_cost.return_value = 2.57
        out = estimate_cost("MNQZ6", self.START, self.END, client=client)
        self.assertEqual(out["estimated_usd"], 2.57)
        client.timeseries.get_range.assert_not_called()
        self.assertEqual(client.metadata.get_cost.call_args.kwargs["schema"], "ohlcv-1m")

    def test_must_confirm_and_cap(self):
        client = MagicMock()
        client.metadata.get_cost.return_value = 1.1
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(PermissionError):
                acquire("MNQZ6", self.START, self.END, t, max_usd=10, client=client)
            with self.assertRaises(PermissionError):
                acquire("MNQZ6", self.START, self.END, t, max_usd=1, acknowledge_charges=True, client=client)
            client.timeseries.get_range.assert_not_called()

    def test_untrusted_vendor_payload_validation(self):
        client = MagicMock()
        client.metadata.get_cost.return_value = 0.12
        ts = [datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(minutes=i) for i in range(3)]
        df = FakeFrame([
            {"open": 20000 + i * .25, "high": 20000.25 + i * .25,
             "low": 19999.75 + i * .25, "close": 20000 + i * .25,
             "volume": 12 + i, "instrument_id": 12} for i in range(3)
        ], ts)
        client.timeseries.get_range.return_value.to_df.return_value = df
        client.timeseries.get_range.return_value.to_file.side_effect = lambda path: Path(path).write_bytes(b"vendor-DBN-test")
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t) / "new"
            result = acquire("MNQZ6", self.START, self.END, folder, max_usd=0.2,
                             acknowledge_charges=True, client=client)
            self.assertEqual(result["row_count"], 3)
            self.assertTrue((folder / "mnq_1m.csv").exists())
            with self.assertRaises(FileExistsError):
                acquire("MNQZ6", self.START, self.END, folder, max_usd=0.2,
                        acknowledge_charges=True, client=client)
            client.timeseries.get_range.assert_called_once()

    def test_mixed_instruments_rejected(self):
        ts = [datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(minutes=i) for i in range(3)]
        store = MagicMock()
        store.to_df.return_value = FakeFrame([
            {"open":20000,"high":20001,"low":19999,"close":20000,
             "volume":10,"instrument_id":i} for i in (1, 2, 1)
        ], ts)
        with self.assertRaisesRegex(ValueError, "multiple instrument"):
            _records(store, "MNQZ6")


class TestNautilusDataContract(unittest.TestCase):
    def test_one_minute_end_timestamps(self):
        bars = synthetic_bars(3, contract=Contract(contract_id="MNQZ6"))
        seen = convert_bars(bars, "MNQZ6", factory=lambda bar, event, init: (event, init))
        self.assertEqual(len(seen), 3)
        self.assertEqual(seen[0][1] - seen[0][0], 60_000_000_000)
        self.assertEqual(seen[1][0] - seen[0][0], 60_000_000_000)

    def test_bad_price_rejected_before_optional_import(self):
        bars = synthetic_bars(3, contract=Contract(contract_id="MNQZ6"))
        bars[0] = type(bars[0])(bars[0].timestamp, bars[0].open + .01,
            bars[0].high, bars[0].low, bars[0].close, bars[0].volume, bars[0].contract_id)
        with self.assertRaises(ValueError):
            convert_bars(bars, "MNQZ6", factory=lambda *_: None)


if __name__ == "__main__":
    unittest.main()
