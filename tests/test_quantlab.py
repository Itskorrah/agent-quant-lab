import csv
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from quantlab.cli import main
from quantlab.dashboard import export_report
from quantlab.market import Bar, Contract, check_bars, load_csv, synthetic_bars, to_csv, write_manifest
from quantlab.notifications import telegram_preview
from quantlab.orchestration import Queue
from quantlab.registry import Registry
from quantlab.research import experiment, final_holdout, quality_report
from quantlab.sim import Settings, signal, simulate


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.contract = Contract()
        self.bars = synthetic_bars(180)

    def test_contract_arithmetic(self):
        with self.assertRaises(ValueError):
            Contract(tick_value=1.0)

    def test_valid_data_has_no_gaps(self):
        self.assertEqual(check_bars(self.bars, self.contract, expected_seconds=60)["unexpected_interval_count"], 0)

    def test_non_utc_fails(self):
        from datetime import timezone
        self.bars[2] = replace(self.bars[2], timestamp=self.bars[2].timestamp.replace(tzinfo=timezone(timedelta(hours=10))))
        with self.assertRaisesRegex(ValueError, "UTC"):
            check_bars(self.bars, self.contract)

    def test_duplicate_fails(self):
        self.bars[3] = replace(self.bars[3], timestamp=self.bars[2].timestamp)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            check_bars(self.bars, self.contract)

    def test_contract_mismatch_fails(self):
        self.bars[3] = replace(self.bars[3], contract_id="OTHER")
        with self.assertRaisesRegex(ValueError, "contract ID"):
            check_bars(self.bars, self.contract)

    def test_ohlc_outside_range_fails(self):
        self.bars[3] = replace(self.bars[3], high=self.bars[3].low)
        with self.assertRaisesRegex(ValueError, "OHLC"):
            check_bars(self.bars, self.contract)

    def test_tick_violation_fails(self):
        self.bars[3] = replace(self.bars[3], close=self.bars[3].close + 0.12)
        with self.assertRaisesRegex(ValueError, "tick"):
            check_bars(self.bars, self.contract)

    def test_gaps_reported_not_silently_filled(self):
        gaps = [b for i, b in enumerate(self.bars) if i != 50]
        self.assertEqual(check_bars(gaps, self.contract, expected_seconds=60)["unexpected_interval_count"], 1)

    def test_csv_roundtrip_and_manifest_immutability(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "bars.csv"
            to_csv(csv_path, self.bars)
            returned, meta = load_csv(csv_path, self.contract)
            self.assertEqual(returned, self.bars)
            path = write_manifest(Path(tmp) / "dataset", meta)
            self.assertTrue(path.exists())
            with self.assertRaises(FileExistsError):
                write_manifest(Path(tmp) / "dataset", {"different": True})

    def test_corrupt_csv_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("timestamp,open\n2026,10\n")
            with self.assertRaisesRegex(ValueError, "columns"):
                load_csv(path, self.contract)


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.bars = synthetic_bars(260)
        self.contract = Contract()

    def test_deterministic_replay(self):
        a = simulate(self.bars, self.contract, Settings())
        self.assertEqual(a, simulate(self.bars, self.contract, Settings()))

    def test_accounting_matches_fills(self):
        result = simulate(self.bars, self.contract, Settings())
        net = sum(t["net_pnl"] for t in result["trades"])
        self.assertAlmostEqual(result["metrics"]["net_pnl"], net, places=2)
        self.assertEqual(len(result["fills"]), 2 * len(result["trades"]))

    def test_costs_hurt_performance(self):
        cheap = simulate(self.bars, self.contract, Settings(fee_per_side=0, slippage_ticks=0))
        dear = simulate(self.bars, self.contract, Settings(fee_per_side=10, slippage_ticks=8))
        self.assertGreaterEqual(cheap["metrics"]["net_pnl"], dear["metrics"]["net_pnl"])

    def test_future_data_does_not_affect_signal(self):
        a = signal(self.bars, 50, 20, "breakout")
        self.bars[51] = replace(self.bars[51], close=self.bars[51].close + 10000)
        self.assertEqual(a, signal(self.bars, 50, 20, "breakout"))

    def test_margin_blocks_entry(self):
        result = simulate(self.bars, self.contract, Settings(margin_per_contract=10**9))
        self.assertEqual(result["metrics"]["trade_count"], 0)
        self.assertIn("illustrative_margin_insufficient", result["risk_events"])

    def test_risk_halts(self):
        result = simulate(self.bars, self.contract, Settings(max_daily_loss=0.01))
        self.assertIn("daily_loss_limit", result["risk_events"])

    def test_invalid_settings(self):
        with self.assertRaises(ValueError):
            Settings(max_contracts=100)


class ResearchTests(unittest.TestCase):
    def test_holdout_reserved(self):
        bars = synthetic_bars(500)
        result = experiment(bars, Contract(), Settings(), synthetic=True)
        self.assertNotIn("holdout", result)
        self.assertEqual(result["holdout_reserved"]["rows"], 100)
        self.assertFalse(result["eligible_for_paper"])
        self.assertFalse(quality_report(result["validation"])["all_pass"])

    def test_holdout_requires_real_data_and_freeze(self):
        bars = synthetic_bars(500)
        with self.assertRaises(PermissionError):
            final_holdout(bars, Contract(), Settings(), frozen=False, synthetic=False)
        with self.assertRaises(PermissionError):
            final_holdout(bars, Contract(), Settings(), frozen=True, synthetic=True)

    def test_registry_immutable_and_approval_scope(self):
        with tempfile.TemporaryDirectory() as tmp, Registry(Path(tmp) / "runs.sqlite") as r:
            rid = r.save({"result": 2}, kind="synthetic")
            self.assertEqual(rid, r.save({"result": 2}, kind="synthetic"))
            self.assertEqual(r.get(rid), {"result": 2})
            with self.assertRaises(ValueError):
                r.review(rid, reviewer="person", decision="approve_live", reason="test")
            r.review(rid, reviewer="person", decision="reject", reason="not robust")
            self.assertEqual(r.list()[0]["decision"], "reject")

    def test_queue_enforces_handoff(self):
        with tempfile.TemporaryDirectory() as tmp, Queue(Path(tmp) / "tasks.sqlite") as q:
            rid = q.enqueue("researcher", {"idea": "opening range"})
            with self.assertRaises(PermissionError):
                q.handoff(rid, "developer", {})
            q.transition(rid, status="running")
            q.transition(rid, status="completed", result={"spec": "ok"})
            dev = q.handoff(rid, "developer", {"spec": "ok"})
            self.assertEqual(len(q.list()), 2)
            with self.assertRaises(ValueError):
                q.transition(rid, status="running")
            with self.assertRaises(PermissionError):
                q.handoff(dev, "risk_officer", {})

    def test_escaped_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = export_report({"validation": {"metrics": {"net_pnl": "<script>alert(1)</script>"}}}, Path(tmp) / "r.html")
            contents = path.read_text()
            self.assertNotIn("<script>", contents)
            self.assertIn("&lt;script&gt;", contents)

    def test_notification_whitelist(self):
        with self.assertRaises(ValueError):
            telegram_preview({"type": "secret_dump"})

    def test_cli_demo_full_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "demo"
            self.assertEqual(main(["demo", "--out", str(out)]), 0)
            self.assertTrue((out / "report.html").exists())
            report = json.loads((out / "report.json").read_text())
            self.assertFalse(report["eligible_for_live"])
            self.assertFalse(report["quality_gate"]["all_pass"])


if __name__ == "__main__":
    unittest.main()
