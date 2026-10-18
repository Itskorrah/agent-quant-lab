# Product roadmap — evidence-driven milestones

This document distinguishes implemented paths from planned integrations. A checkbox is complete only when tested via the application path, not because a stub exists.

| Stage | Deliverable | State | Objective acceptance test |
| --- | --- | --- | --- |
| 0 | Local import, sample backtest and reports | **Implemented (simplified)** | Demo, CSV roundtrip and trade reconciliation tests |
| 1 | Real MNQ vendor data adapter, licence record and session calendar | **Blocked on vendor access** | Obtain and validate contract-specific data; reconcile provider counts |
| 2 | Multi-contract roll handling and independently checked NautilusTrader engine | **Not implemented** | Test contract mapping, fee and fill correctness with published fixture |
| 3 | Walk-forward optimisation with purging/embargo and one-use holdout gate | **Partial — rolling folds + sensitivity** | Demonstrate intentional leakage rejection, reproduce locked holdout |
| 4 | Robust multiple-testing/statistical inference and sensitivity tests | **Not implemented** | Negative controls and false discovery diagnostics |
| 5 | Rich local UI, strategy comparison and chart-based trade inspection | **Offline HTML plots + trades** | Browser journey over at least two stored experiments |
| 6 | Hermes agent execution + Codex SDK/CLI sandboxed adapter | **Protocol only** | Independent agent tasks, bounded execution and permissions tested |
| 7 | Exchange-data-driven paper mode with realistic simulated order lifecycle | **Offline replay + audit journal** | Network disconnect/restart/reconciliation and risk halts tested |
| 8 | Telegram authorised notifications, scheduler and monthly usage caps | **Sender implemented (mocked), scheduler absent** | Live delivery test to authorised account, no secrets in logs |
| 9 | Unattended health checks, backups, recovery and audit evidence | **Not implemented** | Restart/recovery drill, incident report and reproducible state |
| 10 | Live brokerage connectivity | **Explicitly out of scope** | Separate explicit authorisation and independent security review required |

## Build order

1. Validate sample vendor data and session boundaries. Never silently forward-fill gaps.
2. Add independent event-driven backtesting against actual MNQ contracts, commissions and roll events.
3. Build experiment comparisons with an untouched holdout and multiple-testing correction.
4. Add an interactive local dashboard and reproducible replay debugger.
5. Connect Hermes to constrained JSON task contracts and Codex in isolated worktrees.
6. Integrate licensed streaming data and a persistent, fail-closed paper engine.
7. Add operational incident tests, monitoring, cost budgets, Telegram and backup.

## Governance and promotion

A strategy can be researched without any approval, but a backtest result never authorises paper or live trading. Holdout access must be logged and parameter freezing independently verified. Paper entry requires a manual authorisation workflow developed in a later milestone; the present `approve_replay` registry state authorises **offline replay only**. Risk controls must remain outside model-editable code. Do not collapse validator and developer permissions into one agent.
