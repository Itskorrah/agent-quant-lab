# Hermes + Codex integration contract (design, not active integration)

The current `quantlab.orchestration.Queue` is a deterministic local protocol that could back Hermes specialist bot tools. It does **not** run Hermes, send requests to LLMs or consume Codex subscription usage.

## Agent responsibilities

| Bot | Inputs | Outputs | Privilege boundary |
| --- | --- | --- | --- |
| coordinator | research goal, experiment state | task plan | cannot grant trading permission |
| data_steward | raw licensed inputs | integrity evidence | read-only data checks |
| researcher | clean observations, prior research | falsifiable strategy spec | no write to policy |
| developer | approved spec, scoped branch | tests and code proposal | isolated worktree, no production secrets |
| backtest_runner | pinned commit, contract, data hash | immutable evidence | bounded offline simulation |
| validator | code, evidence, holdout policy | reject/review decision | no code modification |
| risk_officer | complete reports | independent veto/pause | cannot self-authorise |
| paper_observer | manually approved candidate | simulated events | offline replay until later milestone |
| performance_monitor | simulated trade ledger | deterioration investigation | alert/research only |

`Queue.handoff()` restricts the initial transfer graph. Tasks are persisted in SQLite with strict state transitions. Production integration needs leases, idempotency, retry budgets, identity/signatures, role-specific credentials, sandboxing and independent service-level risk gates.

## Proposed Hermes adapter workflow

1. Hermes coordinator receives bounded user research objective.
2. Bot invokes a *scoped* queue tool with JSON task schema; no raw shell execution.
3. Researcher writes an experiment specification with data and time constraints.
4. Human-reviewed code-generation adapter dispatches to Codex in an isolated branch/worktree.
5. Runner verifies version, input checksum and budget before executing backtest.
6. Validator independently checks leakage, data integrity and cost sensitivity.
7. Registry archives all results, including failures. Alerts only summarise evidence.
8. No automatic trading or paper promotion; human review is separate.

### Example offline queue usage

```python
from quantlab.orchestration import Queue
with Queue('runs/tasks.db') as q:
    task_id = q.enqueue('researcher', {'hypothesis': 'Does opening-range behaviour persist after costs?'})
    q.transition(task_id, status='running')
    q.transition(task_id, status='completed', result={'spec_path': 'specs/hypothesis-001.json'})
    next_id = q.handoff(task_id, 'developer', {'spec_path': 'specs/hypothesis-001.json'})
```

No side effects outside the local SQLite file occur. Configure model providers and Telegram only after security and cost review. Do not equate the local protocol with deployed autonomous agents.
