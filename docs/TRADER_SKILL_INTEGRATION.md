# Selective trader-skill integration — MNQ research context

Source considered: [Jakeschincariol/trader-skill](https://github.com/Jakeschincariol/trader-skill), MIT licensed, inspected from its initial `5189e79b9a480755a3733ac9713f5353981dbe18` commit (14 October 2026).

This is an **original, limited adaptation of engineering ideas**, not a wholesale copy of that stock-trading package. No external package install, brokerage authentication, stock orders, live trades, paid data, or agent-controlled risk policy was added.

## Included

| Original pattern | Agent Quant Lab equivalent | Why |
| --- | --- | --- |
| Budget sizing / pre-order risk controls | `quantlab/risk_preview.py` | Quantifies a hypothetical MNQ stop risk including slippage, both sides of execution, fees and session-loss headroom; conservative single-contract cap |
| SEC filings / news monitoring | `quantlab/sec_intelligence.py` | Captures market context from official SEC EDGAR submissions, with content hashes, explicit observations, bounded watchlists and immutable output |
| Strict approval separation | No approval/execution path created | Existing repository policy requires independent authorisation and prohibits brokers |

### Use the MNQ risk preview

The example is **synthetic research input**, not an actual trade or margin quote. Copy it to a project-local ignored directory, adjust as required and explicitly name a contract.

```bash
python -m quantlab risk-preview \
  --proposal config/mnq-risk-proposal.example.json \
  --contract MNQ-DEMO \
  --out runs/risks/example.json
```

Input fields: `contract_id`, `direction` (`long`/`short`), `stop_ticks` (positive integer), `risk_budget_usd`, `max_session_loss_usd`, optional `session_realised_loss_usd`, `round_trip_fee_usd` (total for entry+exit, defaults to USD $3), `slippage_ticks` (per side, defaults to 2), and `existing_contracts`. Optional `available_cash_usd` and `assumed_margin_per_contract_usd` must occur together. Their use does **not** independently verify real margin requirements.

Loss estimate per contract = `stop_ticks × $0.50 + 2 × slippage_ticks × $0.50 + round_trip_fee_usd`. The gate compares estimated risk to the smaller of the trade budget and the remaining declared session loss limit. It refuses the proposal when an existing contract already occupies the project's single-contract research cap. Output contains a proposal SHA-256 fingerprint, blocked reasons, conservative risk values, explicit caveats and `eligible_for_live=false`, `eligible_for_paper=false`.

**Never interpret `within_research_limits` as a green light to place a trade.** Stops may gap or slip beyond this assumption; the simulator itself does not have live stops. Session boundaries are supplied, not independently matched to CME. Actual margin varies by broker.

### Use SEC filing intelligence

The example watchlist includes several large listed US technology companies as **context**. This does not assume individual companies predict MNQ prices.

To collect official public submissions by deliberate user request, set a contact string such as `SEC_USER_AGENT='Research Agent contact@example.com'` in your local environment, then:

```bash
python -m quantlab sec-filings \
  --watchlist config/sec-watchlist.example.json \
  --fetch --since 2026-10-01 --out runs/sec/snapshot-001.json
```

For deterministic offline review, save permitted SEC responses under `CIK0001045810.json` etc. Use an **honest observation time**; you must not backdate a modern download to make it appear historically available:

```bash
python -m quantlab sec-filings \
  --watchlist config/sec-watchlist.example.json \
  --offline-dir data/sec-captures \
  --observed-at 2026-10-21T00:00:00Z \
  --since 2026-10-01 --out runs/sec/offline-001.json
```

The SEC client reads only `https://data.sec.gov/submissions/CIK{cik}.json`; only `8-K`, `10-K` and `10-Q` records are retained. No network is used without `--fetch`. There are caps on watchlist length and response size. Outputs identify every feed with its SHA-256, label fetched versus user-declared observation time, and fail on conflicting CIKs or malformed accessions.

SEC filing dates are day-level. Its `acceptanceDateTime` value has no explicit time-zone offset in these records; the tool preserves it as `acceptance_time_unzoned`, **not** a verified UTC event time. These records are not automatically eligible for minute-level backtesting, trading decisions, paper promotions, or agent execution. A historically correct event-time pipeline requires verified availability timestamps, market sessions and independent validation.

Snapshots use exclusive file creation, so rerunning with the same `--out` refuses to overwrite existing research evidence.

### Compare saved SEC observations

```bash
python -m quantlab sec-diff \
  --previous runs/sec/snapshot-001.json \
  --current runs/sec/snapshot-002.json \
  --out runs/sec/newly-observed.json
```

The diff enforces the same watchlist, chronological UTC observation times and compatible snapshot schema. It reports accessions **newly observed between these two snapshots**, not proof that filings were freshly published. Changes to collection filters/SEC history and unverified announcement timestamps prevent this from being a backtest-ready release-event detector.


## Excluded intentionally

- 13F/Buffett copycat: quarterly lag and only partial exposures, not suitable for automated MNQ entries.
- Congressional/Pelosi tracker: trades may be disclosed weeks later; not a real-time signal.
- Equity portfolio rebalancing, stock screening and US wash-sale taxation: unrelated to this futures-focused research project and Australian taxation.
- Broker/Alpaca/IBKR order tickets and automatic permissions: conflict with `AGENTS.md` and `config/policy.json`.
- Any assumption that filings, news or LLM interpretation add alpha: unproven without pre-registered out-of-sample evaluation.

## Testing and safe operation

```bash
python -m unittest discover -s tests -v
python -m pytest -q
python -m quantlab demo --out runs/demo
```

New offline tests cover invalid input, risk arithmetic, single-contract cap, implied margin assumptions, source hashes, de-duplication, CLI writes, timezone checks and fixed SEC network endpoint mocks. Network responses and actual broker execution are **not** exercised by tests. Core simulator and policy are unchanged.

The existing research-only policy remains binding: no brokerage connection, live execution, paper auto-promotion, untrusted code execution or use of research evidence as financial advice.
