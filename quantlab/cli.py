"""Local CLI: no brokers, network clients or automatic trading."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dashboard import export_report
from .market import Contract, load_csv, synthetic_bars, to_csv, write_manifest
from .notifications import telegram_preview
from .validation import rolling_validation, sensitivity
from .journal import record_replay, verify as verify_journal
from .telegram import send_preview
from .orchestration import Queue
from .registry import Registry
from .research import experiment, final_holdout, quality_report
from .sim import Settings, simulate


def json_file(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quantlab", description="Local MNQ research; broker access not implemented")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Generate explicitly SYNTHETIC prices and evaluate a strategy")
    demo.add_argument("--out", default="runs/demo")
    imp = sub.add_parser("import-csv", help="Validate licensed historical OHLCV CSV, no downloads")
    imp.add_argument("--csv", required=True)
    imp.add_argument("--contract", required=True, help="Actual futures contract identifier")
    imp.add_argument("--provider", required=True)
    imp.add_argument("--licence", required=True, help="Description of licence/entitlement")
    imp.add_argument("--dataset", required=True, help="New immutable dataset directory")
    imp.add_argument("--seconds", type=int, default=None, help="Expected interval; irregular intervals are reported")
    back = sub.add_parser("research", help="Run historical research on user-provided CSV")
    back.add_argument("--csv", required=True)
    back.add_argument("--contract", required=True)
    back.add_argument("--registry", default="runs/registry.db")
    back.add_argument("--out", default="runs/research/report.json")
    back.add_argument("--strategy", choices=["breakout", "mean_reversion"], default="breakout")
    replay = sub.add_parser("replay", help="Offline simulation using historical CSV, NOT live paper orders")
    replay.add_argument("--csv", required=True)
    replay.add_argument("--contract", required=True)
    replay.add_argument("--out", default="runs/replay/report.json")
    replay.add_argument("--strategy", choices=["breakout", "mean_reversion"], default="breakout")
    walk = sub.add_parser("walk-forward", help="Evaluate chronological validation folds, reserve final holdout")
    walk.add_argument("--csv", required=True)
    walk.add_argument("--contract", required=True)
    walk.add_argument("--folds", type=int, default=3)
    walk.add_argument("--gap", type=int, default=0)
    walk.add_argument("--out", default="runs/validation/report.json")
    stress = sub.add_parser("sensitivity", help="Run first-60-percent cost/parameter matrix")
    stress.add_argument("--csv", required=True)
    stress.add_argument("--contract", required=True)
    stress.add_argument("--out", default="runs/validation/sensitivity.json")
    audit = sub.add_parser("journal-verify", help="Verify an existing offline replay hash-chain journal")
    audit.add_argument("--file", required=True)
    html = sub.add_parser("html", help="Export a self-contained read-only HTML report")
    html.add_argument("--report", required=True)
    html.add_argument("--out", default="runs/report.html")
    tasks = sub.add_parser("tasks", help="List local Hermes-compatible handoff queue")
    tasks.add_argument("--db", default="runs/tasks.db")
    notify = sub.add_parser("notify-preview", help="Format a message, without sending it")
    notify.add_argument("--type", choices=["research_complete", "validation_failed", "paper_halted", "data_failure"], required=True)
    notify.add_argument("--reason", default="")
    sending = sub.add_parser("notify-send", help="Send one manually approved research preview to allowlisted Telegram chat")
    sending.add_argument("--type", choices=["research_complete", "validation_failed", "paper_halted", "data_failure"], required=True)
    sending.add_argument("--reason", default="")
    sending.add_argument("--confirm-send", action="store_true")
    args = parser.parse_args(argv)
    contract = Contract(contract_id=getattr(args, "contract", "MNQ-DEMO"))
    if args.command == "demo":
        base = Path(args.out)
        bars = synthetic_bars(contract=contract)
        to_csv(base / "synthetic.csv", bars)
        report = experiment(bars, contract, Settings(), synthetic=True)
        report["quality_gate"] = quality_report(report["validation"])
        json_file(base / "report.json", report)
        export_report(report, base / "report.html")
        print("SYNTHETIC demonstration completed — not evidence of trading performance")
        print("Report:", base / "report.html")
    elif args.command == "import-csv":
        if args.contract == "MNQ-DEMO":
            parser.error("Real CSV requires a real contract ID")
        bars, details = load_csv(args.csv, contract, expected_seconds=args.seconds)
        details.update({"provider": args.provider, "licence": args.licence,
                        "data_kind": "user-supplied-historical", "bars": len(bars)})
        target = write_manifest(Path(args.dataset), details)
        print("Validated manifest:", target)
        if details["unexpected_interval_count"]:
            print("WARNING: unexpected intervals:", details["unexpected_interval_count"])
    elif args.command in ("research", "replay", "walk-forward", "sensitivity"):
        if args.contract == "MNQ-DEMO":
            parser.error("Historical CSV requires actual contract ID")
        bars, details = load_csv(args.csv, contract)
        cfg = Settings(strategy=getattr(args, "strategy", "breakout"))
        if args.command == "walk-forward":
            report = rolling_validation(bars, contract, cfg, folds=args.folds, gap=args.gap)
            report["dataset"] = details
        elif args.command == "sensitivity":
            report = sensitivity(bars, contract, cfg)
            report["dataset"] = details
        elif args.command == "research":
            report = experiment(bars, contract, cfg, synthetic=False)
            report["quality_gate"] = quality_report(report["validation"])
            report["dataset"] = details
            with Registry(args.registry) as reg:
                identifier = reg.save(report, kind="historical")
            report["experiment_id"] = identifier
        else:
            report = simulate(bars, contract, cfg)
            report["mode"] = "offline_replay_not_live_paper"
            report["dataset"] = details
            report["eligible_for_live"] = False
            report["journal"] = record_replay(Path(args.out).with_suffix(".jsonl"), report)
        json_file(args.out, report)
        print("Created", args.out, "— live and automatic orders disabled")
    elif args.command == "html":
        result = json.loads(Path(args.report).read_text(encoding="utf-8"))
        print(export_report(result, args.out))
    elif args.command == "journal-verify":
        print(json.dumps(verify_journal(args.file), indent=2))
    elif args.command == "tasks":
        with Queue(args.db) as queue:
            print(json.dumps(queue.list(), indent=2))
    elif args.command == "notify-preview":
        print(telegram_preview({"type": args.type, "reason": args.reason}))
    elif args.command == "notify-send":
        message = telegram_preview({"type": args.type, "reason": args.reason})
        print(json.dumps(send_preview(message, confirmed=args.confirm_send)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
