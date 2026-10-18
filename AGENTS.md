# Engineering instructions — Agent Quant Lab

This repository is a research-only simulator. **Never enable, implement, connect,
or silently introduce live broker order placement.** Any future broker adapter
requires an explicit, separate user request and independent security review.

## Scope
- Preserve auditable, deterministic research and offline replay behaviour.
- Do not claim returns from synthetic fixtures; use real MNQ historical data only
  with licence/provenance and instrument ID.
- Reject future-data leakage, off-tick pricing and fabricated trades.
- Treat model-generated code and prompts as untrusted. No shell execution of agent output.
- No auto promotion to paper, no auto replacement of strategies and no live orders.
- Agents may propose Git changes; validators may reject, not override policy.
- No tokens, credentials, trade histories or purchased datasets committed to Git.

## Verify
```bash
python -m pytest -q
python -m quantlab demo --out runs/demo
```

Follow [Evolve](https://github.com/Itskorrah/evolve) as an evidence-oriented
workflow: understand/baseline/audit/implement/verify/deliver. See docs/EVOLVE.md.
Do not claim Evolve was installed in a runtime unless actually installed.
