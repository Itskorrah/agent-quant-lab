import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quantlab.analytics import trade_statistics, utc_daily_statistics
from quantlab.bridge import enqueue_request, enqueue_json_file
from quantlab.cli import main
from quantlab.dashboard import export_report
from quantlab.journal import append, verify, record_replay
from quantlab.market import Contract, synthetic_bars, to_csv
from quantlab.orchestration import Queue
from quantlab.sim import Settings, simulate
from quantlab.telegram import send_preview
from quantlab.validation import rolling_validation, sensitivity


class ExtendedTests(unittest.TestCase):
    def setUp(self):
        self.bars = synthetic_bars(500)
        self.contract = Contract()

    def test_statistics_unavailable_for_insufficient_days(self):
        run = simulate(self.bars, self.contract, Settings())
        self.assertIsNone(run["daily_statistics"]["daily_sharpe"])
        self.assertEqual(run["trade_statistics"]["count"], run["metrics"]["trade_count"])

    def test_trade_statistics_no_fake_profit_factor(self):
        stats = trade_statistics([{"net_pnl": 10}, {"net_pnl": -5}, {"net_pnl": 4}])
        self.assertEqual(stats["profit_factor"], 2.8)
        self.assertEqual(stats["net_pnl"], 9)

    def test_rolling_reserves_holdout_and_is_deterministic(self):
        a = rolling_validation(self.bars, self.contract, Settings(), folds=3, gap=2)
        self.assertEqual(len(a["folds"]), 3)
        self.assertEqual(a, rolling_validation(self.bars, self.contract, Settings(), folds=3, gap=2))
        self.assertEqual(a["reserved_holdout_rows"], 100)
        self.assertTrue(all(f["gap_bars"] == 2 for f in a["folds"]))
        altered = self.bars[:]
        from dataclasses import replace
        altered[-1] = replace(altered[-1], close=altered[-1].close + 100)
        self.assertEqual(a, rolling_validation(altered, self.contract, Settings(), folds=3, gap=2))

    def test_rolling_rejects_insufficient_data(self):
        with self.assertRaises(ValueError):
            rolling_validation(self.bars[:70], self.contract, Settings(), folds=5)

    def test_parameter_sensitivity_only_training(self):
        out = sensitivity(self.bars, self.contract, Settings())
        self.assertEqual(len(out["runs"]), 9)
        self.assertFalse(out["eligible_for_paper"])
        self.assertEqual(out["sample"], "first_60_percent_only")

    def test_sensitivity_bad_inputs(self):
        with self.assertRaises(ValueError):
            sensitivity(self.bars, self.contract, Settings(), lookbacks=(1,))
        with self.assertRaises(ValueError):
            sensitivity(self.bars, self.contract, Settings(), extra_cost_ticks=(-1,))

    def test_journal_hash_chain_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            append(path, {"action": "created"})
            append(path, {"action": "reviewed"})
            self.assertEqual(verify(path)["events"], 2)
            content = path.read_text()
            path.write_text(content.replace("created", "tampered"))
            with self.assertRaisesRegex(ValueError, "hash"):
                verify(path)
            with self.assertRaises(ValueError):
                append(path, {"action": "more"})

    def test_replay_journal_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.jsonl"
            result = simulate(self.bars, self.contract, Settings())
            self.assertGreater(record_replay(path, result)["events"], 2)
            with self.assertRaises(FileExistsError):
                record_replay(path, result)

    def test_hermes_request_budget_and_privileged_roles(self):
        with tempfile.TemporaryDirectory() as tmp, Queue(Path(tmp) / "tasks.db") as queue:
            with self.assertRaises(ValueError):
                enqueue_request(queue, {"role": "researcher", "request_id": "A", "command": "rm -rf /"})
            with self.assertRaises(ValueError):
                enqueue_request(queue, {"role": "researcher", "request_id": "A", "budget_usd": 100})
            with self.assertRaises(PermissionError):
                enqueue_request(queue, {"role": "paper_observer", "request_id": "A"})
            req = {"role": "researcher", "request_id": "A", "hypothesis": "test"}
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(req))
            tid = enqueue_json_file(queue, path)
            self.assertEqual(queue.list()[0]["id"], tid)

    def test_html_equity_svg_and_trade_table_are_readonly(self):
        run = simulate(self.bars, self.contract, Settings())
        with tempfile.TemporaryDirectory() as tmp:
            html = export_report(run, Path(tmp) / "report.html").read_text()
            self.assertIn("<svg", html)
            self.assertIn("Simulated trades", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("<script", html)

    def test_telegram_requires_opt_in(self):
        msg = "[Agent Quant Lab | simulation/research] test"
        with self.assertRaises(PermissionError):
            send_preview(msg, confirmed=False)
        with self.assertRaises(PermissionError):
            send_preview(msg, confirmed=True, env={})
        with self.assertRaises(PermissionError):
            send_preview(msg, confirmed=True, env={"QUANTLAB_TELEGRAM_BOT_TOKEN": "x", "QUANTLAB_TELEGRAM_CHAT_ID": "999"})

    def test_telegram_sender_mocked_no_real_network(self):
        msg = "[Agent Quant Lab | simulation/research] test"
        from unittest.mock import MagicMock
        context = MagicMock()
        context.__enter__.return_value.read.return_value = b'{"ok":true,"result":{"message_id":42}}'
        environment = {"QUANTLAB_TELEGRAM_BOT_TOKEN": "TEST_TOKEN", "QUANTLAB_TELEGRAM_CHAT_ID": "1",
                       "QUANTLAB_TELEGRAM_ALLOWED_CHATS": "1,2"}
        with patch("quantlab.telegram.urlopen", return_value=context) as fn:
            receipt = send_preview(msg, confirmed=True, env=environment)
            self.assertEqual(receipt["message_id"], 42)
            self.assertEqual(fn.call_count, 1)

    def test_cli_historical_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            spec = Contract(contract_id="MNQ-TEST-MAR26")
            bars = synthetic_bars(500, contract=spec)
            to_csv(path, bars)
            imp = Path(tmp) / "dataset"
            self.assertEqual(main(["import-csv", "--csv", str(path), "--contract", spec.contract_id,
                                   "--provider", "TEST_FIXTURE_NOT_REAL", "--licence", "synthetic",
                                   "--dataset", str(imp), "--seconds", "60"]), 0)
            self.assertTrue((imp / "manifest.json").exists())
            report = Path(tmp) / "research.json"
            self.assertEqual(main(["research", "--csv", str(path), "--contract", spec.contract_id,
                                   "--out", str(report), "--registry", str(Path(tmp) / "db.sqlite")]), 0)
            self.assertFalse(json.loads(report.read_text())["eligible_for_paper"])
            validation = Path(tmp) / "walk.json"
            self.assertEqual(main(["walk-forward", "--csv", str(path), "--contract", spec.contract_id,
                                   "--out", str(validation)]), 0)
            self.assertEqual(len(json.loads(validation.read_text())["folds"]), 3)
            sens = Path(tmp) / "sens.json"
            self.assertEqual(main(["sensitivity", "--csv", str(path), "--contract", spec.contract_id,
                                   "--out", str(sens)]), 0)
            replay = Path(tmp) / "replay.json"
            self.assertEqual(main(["replay", "--csv", str(path), "--contract", spec.contract_id,
                                   "--out", str(replay)]), 0)
            self.assertTrue(replay.with_suffix(".jsonl").exists())
            self.assertEqual(main(["journal-verify", "--file", str(replay.with_suffix(".jsonl"))]), 0)


if __name__ == "__main__":
    unittest.main()
