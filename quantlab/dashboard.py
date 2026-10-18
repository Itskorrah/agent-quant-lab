"""Self-contained, read-only HTML research evidence with rendered equity and trades."""
from __future__ import annotations

import html
import json
import math
from pathlib import Path


def _safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def _chart(curve: list[dict]) -> str:
    """Small pure-SVG plot; avoids external JS/CDN and html injection."""
    if not curve:
        return "<p>No equity observations.</p>"
    samples = curve[::max(1, len(curve) // 300)]
    values = [float(p["equity"]) for p in samples]
    if any(not math.isfinite(v) for v in values):
        return "<p>Invalid equity data.</p>"
    lo, hi = min(values), max(values)
    scale = (hi - lo) or 1
    xs = [20 + 760 * i / max(1, len(samples) - 1) for i in range(len(samples))]
    coords = " ".join(f"{x:.1f},{180 - (v - lo) / scale * 155:.1f}" for x, v in zip(xs, values))
    return ("<svg viewBox='0 0 800 210' role='img' aria-label='Simulated equity curve' "
            "style='width:100%;max-height:350px;background:#151f2e;border-radius:12px'>"
            "<line x1='20' y1='180' x2='780' y2='180' stroke='#547089'/>"
            f"<polyline fill='none' stroke='#65c8c0' stroke-width='2.5' points='{coords}'/>"
            f"<text x='24' y='21' fill='#a7b9ca' font-size='13'>Max: {_safe(round(hi,2))}</text>"
            f"<text x='24' y='202' fill='#a7b9ca' font-size='13'>Min: {_safe(round(lo,2))}</text>"
            "</svg>")


def _table(trades: list[dict]) -> str:
    if not trades:
        return "<p>No simulated closed trades in this sample.</p>"
    cols = [("Entry", "entry"), ("Exit", "exit"), ("Direction", "side"),
            ("Entry price", "entry_price"), ("Exit price", "exit_price"),
            ("Net P&L", "net_pnl"), ("Exit reason", "reason")]
    head = "".join(f"<th>{_safe(name)}</th>" for name, _ in cols)
    rows = "".join("<tr>" + "".join(f"<td>{_safe(t.get(key, '—'))}</td>" for _, key in cols) + "</tr>"
                   for t in trades[:1000])
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>"


def export_report(report: dict, output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    validation = report.get("validation", report)
    metric = validation.get("metrics", {})
    labels = [("Net P&L (USD)", "net_pnl"), ("Ending equity (USD)", "ending_equity"),
              ("Max drawdown", "max_drawdown"), ("Closed trades", "trade_count")]
    cards = "".join(f"<section class='card'><small>{_safe(label)}</small><h2>{_safe(metric.get(key,'—'))}</h2></section>"
                    for label, key in labels)
    raw = html.escape(json.dumps(report, indent=2, default=str, ensure_ascii=True))
    svg = _chart(validation.get("equity_curve", []))
    trades = _table(validation.get("trades", []))
    stats = validation.get("trade_statistics", {})
    extra = " · ".join(f"{_safe(k.replace('_',' ').title())}: {_safe(v)}" for k, v in stats.items()
                     if k in ("mean_trade", "profit_factor", "gross_profit", "gross_loss"))
    page = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Agent Quant Lab · Research Report</title>
<style>body{{background:#101723;color:#e8edf5;font:16px system-ui;margin:0 auto;padding:4vw;max-width:1180px}}
h1{{letter-spacing:-.04em;font-size:2.6rem}}.muted{{color:#91a3b9}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}
.card{{background:#1c293b;padding:20px;border-radius:14px}}small{{color:#a7b9ca}}h2{{margin-bottom:10px}}
pre{{overflow:auto;background:#182337;padding:20px;border-radius:14px;font-size:12px;max-height:450px}}
.notice{{padding:12px 16px;border-left:4px solid #f4ae58;background:#2b2a27}}
.scroll{{max-height:420px;overflow:auto;border:1px solid #253950;border-radius:14px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #253950;white-space:nowrap}}
th{{position:sticky;top:0;background:#1c293b}}summary{{cursor:pointer;padding:12px 0;color:#a7b9ca}}</style></head>
<body><p class='muted'>RESEARCH / OFFLINE REPLAY ONLY · NO BROKER ACCESS</p><h1>Agent Quant Lab</h1>
<p class='notice'>No verified trading edge. No live orders. Historical or synthetic results are not forward returns.</p>
<div class='cards'>{cards}</div><h2>Simulated equity</h2>{svg}
<p class='muted'>{extra}</p><h2>Simulated trades</h2>{trades}
<details><summary>Inspect complete raw evidence (JSON)</summary><pre>{raw}</pre></details></body></html>"""
    output.write_text(page, encoding="utf-8")
    return output
