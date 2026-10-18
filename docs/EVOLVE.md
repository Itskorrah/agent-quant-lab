# Evolve-inspired engineering record

Source: [Itskorrah/evolve](https://github.com/Itskorrah/evolve), inspected 18 October 2026. This project follows the **understand → baseline → audit → implement → verify → deliver** method. The external skill is not copied, vendored or installed by default, and no unverified host integration is claimed.

## Baseline findings

The preceding local scaffold consisted of a synthetic long-only breakout demonstration, five small tests, basic agent descriptions and workflow documentation. Its naive annualised daily Sharpe metric was unsuitable for intraday data; contract identity, immutable experiment provenance and real agent handoffs were absent. The GitHub target repository was empty when this development pass began.

## Implemented response

- Separated instrument/data validation from simulation, research and reporting.
- Added contract-ID and tick validation, UTC enforcement, file SHA-256 and immutable manifests.
- Added long/short signals, simulated fills and trade reconciliation, margin/loss/drawdown gating.
- Reserved the final holdout instead of calculating it during routine research.
- Added persistent experiment records, manual review metadata and bounded task handoffs.
- Added reproducible offline demo, replay CLI, HTML report, regression tests and blocker register.

## Verification

Run `python -m pytest -q` and `python -m quantlab demo --out runs/demo`. Record actual results for each release; do not describe model confidence or test names as proof of real-market profitability. Before shipping, inspect changed files for secrets and generated data. Host-specific Evolve installation can be done later via the original skill's documented installer when using Codex.

## Deliberate limitations

No fabricated external integrations, no live brokers, no secret credentials in Git and no claims of successful real-data tests. Future work follows docs/ROADMAP.md. The current package is a working **offline engineering reference**.
