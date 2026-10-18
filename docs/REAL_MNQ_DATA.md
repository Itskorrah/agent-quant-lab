# Real MNQ data and NautilusTrader integration — handover

## Decision record (2026-10-18)

- Selected vendor integration: [Databento GLBX.MDP3 historical](https://databento.com/docs/api-reference-historical), raw quarterly futures contract and `ohlcv-1m` only. It requires an API key, a valid account and applicable CME entitlements. A quote uses the metadata service and is not a purchase.
- No provider account, API key or exchange licence was supplied to this agent. Therefore **no actual MNQ data was purchased or retrieved** and no historical profitability was established.
- A public GitHub repository containing TopstepX-derived MNQ CSVs was considered but **not copied or ingested** because redistribution rights could not be verified.
- The optional [NautilusTrader 2.x](https://nautilustrader.io/docs/latest/getting_started/) `BacktestEngine` smoke adapter was implemented from public documentation, but this environment could not download the necessary wheel. Its runtime functionality is **not yet verified**.

## Contract-sensitive data handling

1. Use explicit `MNQ[H/M/U/Z][year]`, e.g. `MNQZ6`, with `stype_in=raw_symbol`, **not** continuous synthetic adjusted prices. Validate actual expiry and contract identity against provider reference metadata before longer backtests.
2. Databento's one-minute OHLCV `ts_event` is **start of interval**; NautilusTrader's `ts_init` is set to **end of interval**. This is covered by deterministic unit tests.
3. Validate prices on 0.25-point increments, volume, chronological UTC timestamps, OHLC consistency and absence of multiple returned instrument IDs. Record unexpected intervals and treat session closures explicitly.
4. Retain the provider-native `.dbn` file privately. The generated CSV is a normalised view. Both files and the provenance JSON are ignored by Git; they remain subject to the vendor's licence.
5. Avoid false claims of precise fills based on bars. Limit/stop order sequence cannot be reconstructed exactly without finer market data.

## Reproduction steps

Prerequisites: supported Python environment, a Databento account and an API key stored in `DATABENTO_API_KEY` locally, verified historical access/entitlements.

Run `python -m pip install -e '.[databento]'`; then use `python -m quantlab databento-quote --symbol MNQZ6 --start 2026-10-01T00:00:00Z --end 2026-10-02T00:00:00Z`. Read the exact estimated USD cost. To download, run `databento-download` with `--out` under `data/`, `--max-usd` set to a cap you actually approve and `--acknowledge-data-charges`. The program performs another cost check immediately before retrieval.

Install NautilusTrader with a known-compatible 2.x prerelease on Python 3.13+ and run the `nautilus-smoke` command against the newly normalised CSV. **This is an unverified optional integration path** until an independent smoke and accounting test succeeds on the actual wheel. Use the `docs/BLOCKERS.md` list to track remaining work.

## Acceptance criteria still missing

- Real vendor data acquired after account owner approval, cost preview and licence check.
- Metadata-derived actual contract activation and expiry, CME trading sessions, contract rolls and independent price checks.
- Runtime test of a pinned NautilusTrader release and valid margin/fees/fill assumptions.
- Trade-by-trade manual fixture reconciliation, recovery/failure cases and appropriate final untouched holdout.

Do **not** move strategy results to validated or paper-approved based solely on this integration.
