"""Export a static, escaped HTML report; no web server exposed by default."""
from __future__ import annotations

import html
import json
from pathlib import Path


def export_report(report: dict, output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    validation = report.get("validation", report)
    metric = validation.get("metrics", {})
    labels = [("Net P&L", "net_pnl"), ("Ending equity", "ending_equity"),
              ("Max drawdown", "max_drawdown"), ("Trades", "trade_count")]
    cards = "".join(f"<section class='card'><small>{html.escape(label)}</small><h2>{html.escape(str(metric.get(key,'—')))}</h2></section>"
                    for label, key in labels)
    raw = html.escape(json.dumps(report, indent=2, default=str, ensure_ascii=True))
    page = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Agent Quant Lab · Research Report</title>
<style>body{{background:#101723;color:#e8edf5;font:16px system-ui;margin:0;padding:4vw;max-width:1100px}}
h1{{letter-spacing:-.04em;font-size:2.6rem}}.muted{{color:#91a3b9}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}
.card{{background:#1c293b;padding:20px;border-radius:14px}}small{{color:#a7b9ca}}pre{{overflow-x:auto;background:#182337;padding:20px;border-radius:14px;font-size:12px}}
.notice{{padding:12px 16px;border-left:4px solid #f4ae58;background:#2b2a27}}</style></head>
<body><p class='muted'>RESEARCH / OFFLINE REPLAY ONLY</p><h1>Agent Quant Lab</h1>
<p class='notice'>No verified trading edge. No live orders. Historical / synthetic results are not forward returns.</p>
<div class='cards'>{cards}</div><h2>Full evidence</h2><pre>{raw}</pre></body></html>"""
    output.write_text(page, encoding="utf-8")
    return output
