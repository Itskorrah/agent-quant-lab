import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from quantlab.batch_dashboard import export_batch
from quantlab.cli import main
from quantlab.discovery import batch_discover
from quantlab.market import Contract, synthetic_bars, to_csv
from quantlab.sim import Settings


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.contract = Contract()
        self.bars = synthetic_bars(500)

    def test_six_candidates_with_holdout_reserved(self):
        result = batch_discover(self.bars, self.contract, synthetic=True)
        self.assertEqual(result["candidate_count"], 6)
        self.assertEqual(result["holdout_reserved"]["bars"], 100)
        self.assertEqual(len(result["candidates"]), 6)
        self.assertFalse(result["eligible_for_live"])
        self.assertFalse(result["eligible_for_paper"])

    def test_future_holdout_changes_do_not_affect_any_result(self):
        before = batch_discover(self.bars, self.contract, synthetic=True)
        later = self.bars[:]
        last = later[-1]
        later[-1] = replace(last, high=last.high + 1000, close=last.close + 1000)
        after = batch_discover(later, self.contract, synthetic=True)
        self.assertEqual(before["candidates"], after["candidates"])
        self.assertEqual(before["selected_candidate"], after["selected_candidate"])
        self.assertNotEqual(before["dataset_sha256"], after["dataset_sha256"])

    def test_repeated_batch_is_deterministic(self):
        a = batch_discover(self.bars, self.contract, synthetic=True)
        self.assertEqual(a, batch_discover(self.bars, self.contract, synthetic=True))

    def test_no_candidate_produces_no_false_winner(self):
        result = batch_discover(self.bars, self.contract, synthetic=True, min_training_trades=10**6)
        self.assertIsNone(result["selected_candidate"])
        self.assertTrue(all(c["training_rejected"] for c in result["candidates"]))

    def test_invalid_candidate_cap_fails(self):
        with self.assertRaises(ValueError):
            batch_discover(self.bars, self.contract, synthetic=True, max_candidates=2)
        with self.assertRaises(ValueError):
            batch_discover(self.bars, self.contract, synthetic=True, strategies=("hindsight",))

    def test_batch_html_generated_and_escaped(self):
        result = batch_discover(self.bars, self.contract, synthetic=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = export_batch(result, Path(tmp) / "index.html")
            page = path.read_text()
            self.assertIn("Candidate comparison", page)
            self.assertIn("breakout-lb20", page)
            self.assertNotIn("<script", page)

    def test_cli_batch_demo_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertEqual(main(["batch-demo", "--out", str(folder / "batch-demo")]), 0)
            self.assertTrue((folder / "batch-demo" / "index.html").exists())
            contract = Contract(contract_id="MNQ-TEST-202603")
            path = folder / "bars.csv"
            to_csv(path, synthetic_bars(500, contract=contract))
            report = folder / "report.json"
            self.assertEqual(main(["batch-discover", "--csv", str(path), "--contract", contract.contract_id,
                                   "--registry", str(folder / "registry.db"), "--out", str(report)]), 0)
            self.assertTrue(report.with_suffix(".html").exists())
            self.assertEqual(json.loads(report.read_text())["candidate_count"], 6)


if __name__ == "__main__":
    unittest.main()
