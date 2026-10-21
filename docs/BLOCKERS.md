# Delivery register: implemented vs blocked

Last reviewed: 18 October 2026.

## External blockers

| Blocker | Impact | Required resolution |
| --- | --- | --- |
| No licensed MNQ data and entitlement supplied | Only deterministic synthetic fixtures tested here | Choose a provider, provide permitted contract-specific CSV, verify coverage/licence |
| No live feed credentials / exchange market-data entitlement | No real-time paper signals | Select compatible live-feed provider, implement adapter, independently test timestamp semantics |
| No Telegram bot token / authorised chat ID | Preview available, one-shot sender coded but live send untested | Configure secrets in local environment; test explicit allowlist |
| No Hermes installation/session credentials | Persistent LLM bot execution unverified | Install Hermes, configure scoped tools/models, test job handoffs |
| No Codex unattended authentication | Automated strategy code generation not connected | Choose permitted Codex SDK/CLI auth path and test bounded worktree delegation |
| No independent NautilusTrader installation or exchange-grade dataset | Simulator remains simplified | Pin compatible version, implement adapter, compare independent fixtures |
| No always-on runtime or backup destination | No unattended reliability guarantees | Choose deployment host, implement recovery and monitoring |
| No brokerage connectivity | Cannot place live orders | Intentionally outside authorised scope; separate review necessary |

## Known engineering gaps

- Single-contract, single-position, one-lot simulated market orders only.
- No continuous futures contract roll, CME calendar or exchange session boundary.
- No bid/ask or depth-of-book; fills approximate bar-open prices plus adverse slippage.
- UTC daily risk reset; bar-close risk liquidation can understate gap losses.
- Validation research does not automatically compute a held-out final result; current separate `final_holdout` guard is not a secure single-use service.
- Fixed-candidate batch discovery, parameter sensitivity and rolling chronological folds exist, but lack statistically sound experiment-selection adjustment or overlap-aware purging/embargo.
- No risk-adjusted Sharpe ratio on intraday price series; left null intentionally.
- No deployed Hermes/LLM workers, event-driven broker gateway or tested real Telegram credentials.
- No independent security penetration test, hosted CI verification or operational incident drill.

## Next delivery gate

A real MNQ historical contract is loaded with a verified provider licence, a session calendar and a comparable independent backtester. Required artefacts: provider source hash, contract ID, bar coverage, rejected rows, independent accounting fixture, cost model and reviewer signoff. No claims of strategy profitability before this evidence exists.

## Selective trader-skill integration validation (21 October 2026)

- SEC client read-only code and offline fixtures are present, but real SEC HTTP requests and latency/availability have not been exercised in this build environment. SEC filing dates and unzoned acceptance timestamps must not be fed to historical one-minute signals.
- The risk preview assumes a **hypothetical** stop distance and user-supplied slippage, fees, session realised loss and optional margin. It is independent of the simulator and cannot enforce actual brokerage position limits or account state. Do not interpret a nominal pass as trade authorisation.
- The SEC diff compares saved snapshots, not real-time exchange-vetted announcement times. Scheduled monitoring, independent news verification and active notifications remain future work.
- Core end-to-end test suite needs execution in an authenticated local clone; the newly written modules were checked using an isolated local harness. Paid GitHub Actions were not run.

## v0.6 — Data and independent engine integration blockers

1. **Account/entitlement (external):** Databento requires an authenticated account/API key and CME data rights. No key provided; historical MNQ not downloaded. `databento-quote` and capped `databento-download` are ready for the account owner to run. Default download blocked absent explicit acknowledgement and cost cap.
2. **Runtime unavailable (environment):** The NautilusTrader 2.x wheel could not be installed due to blocked package-index/network access. `nautilus-smoke` is an experimental API implementation; smoke execution, fills and engine compatibility are unverified.
3. **Contract reference data:** Exchange activation/expiry, roll calendar, margin, actual trading sessions and revised fees remain unimplemented in Nautilus adapter. The runner's metadata is illustrative and performance output cannot be used for decisions.
4. **Research validity:** No real-data independent hand-calculated P&L fixture, comparison between models, exchange quote data, or real forward paper results yet. Fills and costs in Nautilus smoke are optimistic by design.
