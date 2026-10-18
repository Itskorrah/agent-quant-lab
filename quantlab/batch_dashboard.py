"""Comparative read-only candidate leaderboard for deterministic research batches."""
from __future__ import annotations

import html
import json
from pathlib import Path

from .dashboard import _chart, _table, _safe


def export_batch(report: dict, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in report["candidates"]:
        m = c["training_metrics"]
        status = "Insufficient evidence" if c["training_rejected"] else "Eligible for comparison"
        rows.append("<tr>" + "".join(f"<td>{_safe(v)}</td>" for v in
            (c["name"], m["trade_count"], m["net_pnl"], m["max_drawdown"], status)) + "</tr>")
    winner = report.get("selected_candidate")
    details = ("<p>No candidate met the minimum training-trade requirement.</p>" if winner is None else
               f"<h2>Selected on training data: {_safe(winner['name'])}</h2>"
               f"<p>Validation results: {_safe(winner['metrics'])}</p>"
               + _chart(winner["equity_curve"]) + "<h3>Validation trades</h3>" + _table(winner["trades"]))
    page = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Agent Quant Lab — Research Batch</title><style>body{background:#101723;color:#e8edf5;font:16px system-ui;margin:0 auto;padding:4vw;max-width:1150px}
h1{font-size:2.6rem;letter-spacing:-.04em}.notice{background:#302a25;border-left:4px solid #f4ae58;padding:12px 16px}
.grid{background:#1c293b;padding:18px;border-radius:14px;overflow:auto}table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:12px;border-bottom:1px solid #33445a}th{color:#9bb1c7}</style></head><body>
<p>DETERMINISTIC RESEARCH · NO LIVE ORDERS</p><h1>Candidate comparison</h1>
<p class='notice'>Results are historical research only. Neither the winner nor its validation sample establish a profitable trading edge.</p>
<div class='grid'><table><thead><tr><th>Candidate</th><th>Trades</th><th>Training net P&L</th><th>Drawdown</th><th>Screen</th></tr></thead><tbody>""" + "".join(rows) + "</tbody></table></div>" + details + "</body></html>"
    path.write_text(page, encoding="utf-8")
    return path
