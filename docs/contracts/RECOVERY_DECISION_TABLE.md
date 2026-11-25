# Recovery decision table — after a write attempt

Status: initial (week 1), revision 2. Covers only the decision taken after a write attempt, from
the action's **write history** and the declared retry safety. Evidence evaluation, verification,
delivery status, reservations, quarantine and reconciliation deadlines are added in weeks 3, 12,
13, 17 and 18 and will extend this contract.

Implemented by `actraforge.domain.recovery` (`summarize_write_history`, `decide_after_attempt`).

Revision 2 (2026-11-25): decisions are taken over the whole write history of the action, not the
most recent attempt only. Revision 1 allowed a blind resend when a retry attempt was recorded but
not sent after an earlier attempt with unknown outcome (row 1), and a new attempt after a later
attempt was rejected while an earlier one was still unknown (row 4).

## 1. Per-attempt input: `AttemptOutcome`

The current assessment of one write attempt of the action. Assessments are append-only elsewhere;
this is the latest assessment of that attempt (e.g. reconciliation may move an attempt from
`UNKNOWN` to `CONFIRMED_NOT_APPLIED`).

| Member | Meaning |
|---|---|
| `NOT_DISPATCHED` | The durable dispatch guard proves this attempt's request was never sent. A crash after the dispatch intent was recorded is **not** `NOT_DISPATCHED`; it is `UNKNOWN`. |
| `CONFIRMED_APPLIED` | Trusted evidence that the attempt took effect. This is not verified success of the action; verification is a separate step. |
| `CONFIRMED_NOT_APPLIED` | Trusted evidence, of a kind listed in §3, that the attempt did not take effect **and cannot take effect later**. |
| `UNKNOWN` | Anything else: timeout, lost response, connection reset, crash after dispatch, ACK without effect evidence, and every error listed in §3 as not sufficient. |

## 2. Write history: `WriteHistoryOutcome` and `summarize_write_history`

`summarize_write_history(attempts: Sequence[AttemptOutcome]) -> WriteHistoryOutcome` folds the
assessments of **all** attempts of the action (in any order; the result is order-independent):

| # | Condition (evaluated top to bottom) | `WriteHistoryOutcome` |
|---|---|---|
| H1 | Any attempt is `CONFIRMED_APPLIED` | `CONFIRMED_APPLIED` |
| H2 | Else any attempt is `UNKNOWN` | `UNKNOWN` |
| H3 | Else at least one attempt is `CONFIRMED_NOT_APPLIED` (all dispatched attempts are confirmed not applied) | `ALL_CONFIRMED_NOT_APPLIED` |
| H4 | Else (empty history, or every attempt `NOT_DISPATCHED`) | `NO_WRITE_DISPATCHED` |

Notes:

- H1 before H2: one confirmed effect means the next step is verification, never another write.
  Whether a second, unknown attempt could have produced a duplicate EFFECT is a verification and
  attribution concern (weeks 13 and 16), not a reason to write again.
- `NOT_DISPATCHED` attempts never hide an earlier dispatched attempt: they are ignored unless all
  attempts are `NOT_DISPATCHED`.

## 3. Evidence sufficient for `CONFIRMED_NOT_APPLIED`

Only these establish that an attempt did not and cannot later take effect. The full evidence model
(trust, freshness, correlation) arrives in week 13; until then adapters must use this list.

1. A definitive rejection returned **by the target itself** (not a proxy, gateway or load
   balancer) for a request the target documents as not retained after rejection, e.g. schema or
   permission rejection before acceptance.
2. A target-confirmed cancellation or tombstone of the operation (or its operation key) that the
   target guarantees prevents later application.
3. A target-enforced command expiry whose deadline has passed by the target's clock with a
   clock-skew margin, **together with** trusted, fresh, correlated state evidence observed after
   that deadline that the effect is absent. Expiry alone does not prove past non-execution.

Not sufficient, therefore `UNKNOWN`: timeouts; connection errors; HTTP 5xx; 429/rate limiting;
409 or similar "key in use / request in progress / duplicate key" conflicts; any error produced by
an intermediary; a read showing "not applied yet" without one of the guarantees above (a queued
command may still apply later).

## 4. Other inputs

### `RetrySafety` — declared by the trusted action author for the target operation

| Member | Meaning |
|---|---|
| `IDEMPOTENT_WITH_KEY` | The target enforces de-duplication by an operation key, but only inside a bounded window. A retry is safe only with the **same** key and the **same** canonical request while the window is known to be open. |
| `RECONCILE_FIRST` | No target-side de-duplication. Before any further write, trusted evidence must establish that every earlier attempt did not take effect and cannot take effect later. |
| `NEVER_RETRY` | No further write attempt for this action once a write has been dispatched. |

A declared capability is an assumption, not a proven property of the target.

### `IdempotencyWindow` — state of the target's de-duplication window for the operation key

| Member | Meaning |
|---|---|
| `OPEN` | Known to remain open until the retry reaches the target: measured from the **earliest** dispatch of that key, minus a margin covering clock skew **and** the maximum dispatch latency. |
| `CLOSED` | Known to have expired. |
| `UNKNOWN` | Cannot be established. |
| `NOT_APPLICABLE` | The operation has no key/window. |

## 5. Outputs

`RecoveryDecision(kind: DecisionKind, reason: ReasonCode)`; `permits_write` is true only for
`DISPATCH`, `RETRY_SAME_OPERATION_KEY` and `NEW_ATTEMPT`.

| `DecisionKind` | Meaning |
|---|---|
| `DISPATCH` | First dispatch may proceed (no write of this action was ever sent). |
| `PROCEED_TO_VERIFY` | Stop writing; verify the goal through trusted evidence. |
| `RETRY_SAME_OPERATION_KEY` | Resend with the identical target operation key and the identical canonical request (same payload hash). The dispatcher must re-check the window deadline immediately before sending and abort the send if it has passed. |
| `NEW_ATTEMPT` | A new write attempt is safe because every earlier dispatched attempt provably never applies. Key choice for the new attempt is declared by the action author; safety does not depend on it. |
| `RECONCILE` | Do not write; establish the outcome of the earlier attempts first. |
| `STOP` | No further write attempts for this action. |

## 6. Table

`decide_after_attempt(context: RecoveryContext) -> RecoveryDecision`, where `RecoveryContext` has
`write_history: WriteHistoryOutcome`, `retry_safety: RetrySafety`,
`idempotency_window: IdempotencyWindow`. Rows are evaluated top to bottom; the first match wins.
`*` = any value. This table is parsed by `tests/unit/test_recovery_contract_table.py`; keep its
format (backticked members, comma-separated alternatives, `*`).

| # | Write history | Retry safety | Window | Decision | Reason code |
|---|---|---|---|---|---|
| 1 | `NO_WRITE_DISPATCHED` | * | * | `DISPATCH` | `NO_PRIOR_DISPATCH` |
| 2 | `CONFIRMED_APPLIED` | * | * | `PROCEED_TO_VERIFY` | `ATTEMPT_CONFIRMED_APPLIED` |
| 3 | `ALL_CONFIRMED_NOT_APPLIED` | `NEVER_RETRY` | * | `STOP` | `NEVER_RETRY_POLICY` |
| 4 | `ALL_CONFIRMED_NOT_APPLIED` | `IDEMPOTENT_WITH_KEY`, `RECONCILE_FIRST` | * | `NEW_ATTEMPT` | `ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED` |
| 5 | `UNKNOWN` | `IDEMPOTENT_WITH_KEY` | `OPEN` | `RETRY_SAME_OPERATION_KEY` | `UNKNOWN_IDEMPOTENCY_WINDOW_OPEN` |
| 6 | `UNKNOWN` | `IDEMPOTENT_WITH_KEY` | `CLOSED`, `UNKNOWN`, `NOT_APPLICABLE` | `RECONCILE` | `UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED` |
| 7 | `UNKNOWN` | `RECONCILE_FIRST` | * | `RECONCILE` | `UNKNOWN_RECONCILE_FIRST` |
| 8 | `UNKNOWN` | `NEVER_RETRY` | * | `RECONCILE` | `UNKNOWN_NEVER_RETRY` |

Notes:

- Row 1 applies to `NEVER_RETRY` too: if no request of the action was ever sent, nothing has been
  attempted yet.
- Row 8 reconciles to learn the outcome, never to write; if reconciliation moves every attempt to
  `CONFIRMED_NOT_APPLIED`, row 3 stops.
- Row 6: `NOT_APPLICABLE` with `IDEMPOTENT_WITH_KEY` is a contradictory declaration and is treated
  as "window not established" (unsafe default denied).
- After `RECONCILE`, reconciliation updates the assessments of attempts and the history is
  summarized again.
- Liveness gap (known, deferred): rows 6–8 can repeat indefinitely if reconciliation keeps
  returning `UNKNOWN`. Deadlines, backoff and escalation to quarantine/operator are added in weeks
  12 and 18. Staying in `RECONCILE` is safe but not live.

## 7. Input validation

`RecoveryContext` rejects (raises `TypeError`) any field value whose type is not exactly the
declared enum — plain strings and members of other enums included — so that unvalidated values
from storage or interfaces can never obtain a write permission. `summarize_write_history` applies
the same rule to every element.

## 8. Invariants checked by tests

Full enumeration of 4 × 3 × 4 = 48 contexts, plus property tests over attempt sequences.

- INV-R1: `UNKNOWN` history never yields `NEW_ATTEMPT` or `DISPATCH`.
- INV-R2: `RETRY_SAME_OPERATION_KEY` only when history is `UNKNOWN`, safety is
  `IDEMPOTENT_WITH_KEY` and window is `OPEN`.
- INV-R3: `NEVER_RETRY` never yields `NEW_ATTEMPT` or `RETRY_SAME_OPERATION_KEY`.
- INV-R4: `CONFIRMED_APPLIED` history never permits a write.
- INV-R5: `NEW_ATTEMPT` only when history is `ALL_CONFIRMED_NOT_APPLIED`.
- INV-R6: every context yields exactly the decision and reason code of this table.
- INV-R7: `DISPATCH` only if no attempt in the history is `CONFIRMED_APPLIED`,
  `CONFIRMED_NOT_APPLIED` or `UNKNOWN` (i.e. nothing was ever sent).
- INV-R8: once a history contains a dispatched attempt (`CONFIRMED_APPLIED`,
  `CONFIRMED_NOT_APPLIED` or `UNKNOWN`), appending any attempts never yields `NO_WRITE_DISPATCHED`;
  once it contains `UNKNOWN`, appending attempts never yields `ALL_CONFIRMED_NOT_APPLIED`
  (a later rejection cannot clear an earlier unknown).
- INV-R9: `summarize_write_history` is order-independent (any permutation gives the same result).
