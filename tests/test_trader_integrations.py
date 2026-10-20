"""Offline regression checks for trader-skill-inspired research modules."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quantlab.cli import main
from quantlab.market import Contract
from quantlab.risk_preview import assess_proposal
from quantlab.sec_intelligence import (
    watchlist_entries, parse_submissions, scan_watchlist, write_snapshot,
)


class RiskPreviewTests(unittest.TestCase):
    def setUp(self):
        self.p = {"contract_id": "MNQ-TEST", "direction": "long", "stop_ticks": 40,
                  "risk_budget_usd": 100, "max_session_loss_usd": 250,
                  "session_realised_loss_usd": 70, "round_trip_fee_usd": 3,
                  "slippage_ticks": 2}
        self.c = Contract(contract_id="MNQ-TEST")

    def test_one_contract_loss_and_no_execution_authority(self):
        x = assess_proposal(self.p, self.c)
        self.assertEqual(x["per_contract_estimated_loss_usd"], "25.00")
        self.assertEqual(x["status"], "within_research_limits")
        self.assertEqual(x["proposed_contracts"], 1)
        self.assertFalse(x["eligible_for_live"] or x["eligible_for_paper"])
        self.assertEqual(x, assess_proposal(self.p, self.c))

    def test_costs_limits_and_existing_exposure_fail_closed(self):
        x = assess_proposal({**self.p, "risk_budget_usd": 24}, self.c)
        self.assertEqual(x["status"], "blocked")
        self.assertEqual(x["proposed_contracts"], 0)
        self.assertIn("exceeds", x["reasons"][0])
        self.assertEqual(assess_proposal({**self.p, "session_realised_loss_usd": 250}, self.c)["status"], "blocked")
        self.assertEqual(assess_proposal({**self.p, "existing_contracts": 1}, self.c)["status"], "blocked")

    def test_margin_is_only_an_assumption(self):
        with self.assertRaises(ValueError):
            assess_proposal({**self.p, "available_cash_usd": 500}, self.c)
        x = assess_proposal({**self.p, "available_cash_usd": 500,
                             "assumed_margin_per_contract_usd": 1000}, self.c)
        self.assertEqual(x["status"], "blocked")
        self.assertIn("assumption", x["reasons"][-1])

    def test_bad_inputs_fail(self):
        changes = ({"contract_id": "wrong"}, {"direction": "buy"}, {"stop_ticks": 0},
                   {"stop_ticks": True}, {"risk_budget_usd": float("nan")},
                   {"max_session_loss_usd": -5}, {"slippage_ticks": 1.5},
                   {"existing_contracts": 2}, {"unknown_permission": "execute"})
        for data in changes:
            with self.subTest(data=data), self.assertRaises(ValueError):
                assess_proposal({**self.p, **data}, self.c)

    def test_cli_writes_immutable_review_not_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "risk.json"
            out = Path(tmp) / "review.json"
            source.write_text(json.dumps(self.p))
            args = ["risk-preview", "--proposal", str(source),
                    "--contract", "MNQ-TEST", "--out", str(out)]
            self.assertEqual(main(args), 0)
            saved = json.loads(out.read_text())
            self.assertFalse(saved["eligible_for_live"])
            self.assertEqual(saved["status"], "within_research_limits")
            with self.assertRaises(FileExistsError):
                main(args)


class SecTests(unittest.TestCase):
    def setUp(self):
        self.w = {"watchlist": [{"symbol": "NVDA", "cik": "1045810"}]}
        self.payload = {"cik": 1045810, "filings": {"recent": {
            "form": ["8-K", "4", "10-Q", "8-K"],
            "accessionNumber": ["0001045810-26-000001", "0001045810-26-000002",
                                "0001045810-26-000003", "0001045810-26-000001"],
            "filingDate": ["2026-10-01", "2026-10-02", "2026-09-10", "2026-10-01"],
            "acceptanceDateTime": ["2026-10-01T16:01:00", "2026-10-02T16:01:00",
                                   "2026-09-10T16:01:00", "2026-10-01T16:01:00"]}}}

    def test_offline_immutable_snapshot_with_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CIK0001045810.json"
            path.write_text(json.dumps(self.payload))
            report = scan_watchlist(self.w, offline_dir=tmp, observed_at_utc="2026-10-21T00:00:00Z",
                                    since="2026-10-01")
            self.assertEqual(report["filings_count"], 1)
            self.assertEqual(report["filings"][0]["form"], "8-K")
            self.assertEqual(report["filings"][0]["acceptance_time_unzoned"], "2026-10-01T16:01:00")
            self.assertFalse(report["eligible_for_signals"])
            self.assertEqual(len(report["sources"][0]["content_sha256"]), 64)
            out = write_snapshot(Path(tmp) / "snapshot.json", report)
            with self.assertRaises(FileExistsError):
                write_snapshot(out, report)
            self.assertEqual(report, json.loads(out.read_text()))

    def test_reject_bad_watchlist_or_response(self):
        for w in ({"watchlist": []}, {"watchlist": [{"symbol": "../X", "cik": "1"}]},
                  {"watchlist": [{"symbol": "NVDA", "cik": 1}]},
                  {"watchlist": [{"symbol": "NVDA", "cik": "1"}, {"symbol": "NVDA", "cik": "2"}]}):
            with self.assertRaises(ValueError):
                watchlist_entries(w)
        e = watchlist_entries(self.w)[0]
        with self.assertRaisesRegex(ValueError, "CIK mismatch"):
            parse_submissions({**self.payload, "cik": 11}, e)
        with self.assertRaisesRegex(ValueError, "aligned"):
            parse_submissions({"cik": 1045810, "filings": {"recent": {
                "form": ["8-K"], "accessionNumber": [], "filingDate": []}}}, e)
        with self.assertRaises(ValueError):
            scan_watchlist(self.w, offline_dir="unused", fetch=True, observed_at_utc="2026-10-21T00:00:00Z")
        with self.assertRaises(ValueError):
            scan_watchlist(self.w, offline_dir="unused", observed_at_utc="2026-10-21T11:00:00+11:00")

    def test_network_requires_explicit_fetch_and_fixed_sec_endpoint(self):
        with patch("quantlab.sec_intelligence.urlopen") as mocked:
            response = mocked.return_value.__enter__.return_value
            response.read.return_value = json.dumps(self.payload).encode()
            from quantlab.sec_intelligence import fetch_submissions
            raw = fetch_submissions("0001045810", user_agent="Researcher hello@example.com")
            self.assertEqual(json.loads(raw), self.payload)
            self.assertEqual(mocked.call_count, 1)
            request = mocked.call_args.args[0]
            self.assertEqual(request.full_url, "https://data.sec.gov/submissions/CIK0001045810.json")
            with self.assertRaises(ValueError):
                fetch_submissions("../../etc", user_agent="x@y.com")
            with self.assertRaises(ValueError):
                fetch_submissions("0001045810", user_agent="anonymous")

    def test_sec_cli_offline_and_no_trading_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "CIK0001045810.json").write_text(json.dumps(self.payload))
            watch = directory / "watch.json"
            watch.write_text(json.dumps(self.w))
            out = directory / "snapshot.json"
            self.assertEqual(main(["sec-filings", "--watchlist", str(watch), "--offline-dir", str(directory),
                                   "--observed-at", "2026-10-21T00:00:00Z", "--since", "2026-10-01",
                                   "--out", str(out)]), 0)
            snap = json.loads(out.read_text())
            self.assertEqual(snap["filings_count"], 1)
            self.assertFalse(snap["eligible_for_signals"])
            self.assertFalse(snap["eligible_for_live"])
            with self.assertRaises(SystemExit):
                main(["sec-filings", "--watchlist", str(watch), "--offline-dir", str(directory),
                      "--out", str(directory / "out.json")])


if __name__ == "__main__":
    unittest.main()
