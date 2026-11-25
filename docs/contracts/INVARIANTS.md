# Invariants

Status: draft, revision 1 (2026-11-25, week 1). Derived from `Actraforge_ROADMAP.md` §2
(architecture), §3 (core guarantees) and §11 (critical release blockers). Any violation of a
**core** invariant is a release blocker. A passing test suite shows the absence of known
counterexamples, not universal correctness.

## How to read

Each invariant has:

- **Statement** — what must always hold.
- **Source** — roadmap section it is derived from.
- **Layer** — `core` (pure domain), `runtime` (application/infrastructure/interfaces), `lab`.
- **Enforced by** — mechanism (type, decision function, DB constraint, test, review).
- **Checked by** — test location; `planned (week N)` if not yet written.
- **Lab signal** — the Lab metric that would expose a violation, if any.

Status values: **enforced** (mechanism and tests exist), **partial**, **planned**.

Terms: *dispatch* — sending a write request to a target. *Managed write* — a write dispatched by
Actraforge. *Unresolved* — an action whose write history is `UNKNOWN` or which has a command that
may still be pending at the target. *Trusted* — from a source inside the trust boundary as defined
in `EVIDENCE_MODEL.md` (week 2) and `THREAT_MODEL.md`.

---

## 1. Core invariants (INV-01 … INV-20)

### Outcome and evidence

**INV-01 — No false verification.**
An action is `VERIFIED` only on trusted, fresh, correlated evidence that the goal holds. Unknown,
disputed, advisory or acknowledgement-only evidence never yields `VERIFIED`.
Source §3, §11 ("false VERIFIED"). Layer core. Enforced by evidence evaluation (week 3, 13).
Checked by planned (weeks 3, 13). Lab signal: false success. Status: planned.

**INV-02 — Goal, attribution and attestation are separate facts.**
Goal satisfaction, attribution (our execution caused it) and operator attestation/risk acceptance
are recorded as distinct fields. `ALREADY_SATISFIED` (goal held before our dispatch) is never
reported as our execution, and operator attestation is never converted into machine verification.
Source §3. Layer core. Enforced by types (week 2). Checked by planned (weeks 2, 13, 16).
Lab signal: false attribution. Status: planned.

**INV-03 — Append-only history; contradictions become disputes.**
Attempt history, assessments and audit records are append-only. Evidence contradicting a terminal
assessment creates a `DISPUTED` assessment; it never silently overwrites the earlier one.
Source §3. Layer core + runtime (DB). Enforced by pure transitions (week 3) and append-only tables
(week 7). Checked by planned (weeks 3, 7, 13). Status: planned.

**INV-04 — A timeout is not proof of non-execution.**
Timeout, lost response, connection reset or crash after the dispatch intent is durably recorded
yields `UNKNOWN`, never `NOT_DISPATCHED` or `CONFIRMED_NOT_APPLIED`. Only the evidence kinds in
`RECOVERY_DECISION_TABLE.md` §3 establish `CONFIRMED_NOT_APPLIED`.
Source §3. Layer core + runtime. Enforced by recovery contract and dispatch guard (week 11).
Checked by `tests/unit/test_recovery_decision_table.py` (core); crash injection planned (week 11).
Lab signal: unsafe retries. Status: partial.

### Retry and dispatch

**INV-05 — No write without established retry safety.**
After the first dispatched write of an action, every further write requires a recovery decision
with `permits_write`, computed over the action's whole write history. Idempotent retries reuse the
operation key and canonical request inside the enforced window; `RECONCILE_FIRST` requires proof
that no earlier attempt applies; `NEVER_RETRY` allows at most one dispatched write.
Refined by INV-R1 … INV-R9 in `RECOVERY_DECISION_TABLE.md`.
Source §3, §11 ("unsafe write retry"). Layer core + runtime. Enforced by
`actraforge.domain.recovery`; runtime gating planned (week 9, 11).
Checked by `tests/unit/test_recovery_*.py`, `tests/property/test_recovery_properties.py`.
Lab signal: duplicate effects, unsafe retries. Status: partial (core enforced).

**INV-06 — No hidden write retries.**
Each write attempt causes at most one request to reach the target. Temporal write activities have
maximum attempts 1; HTTP/SDK client retries are disabled on write paths.
Source §3. Layer runtime. Enforced by write-client factory and activity options (weeks 9, 11).
Checked by planned (week 11); Lab counter of target-received requests per attempt (week 5, 22).
Lab signal: requests per attempt > 1. Status: planned.

**INV-07 — One executing workflow per action, ever.**
Workflow ID derives deterministically from tenant and action ID. At most one workflow execution
per action dispatches writes — including after dispatcher crash, duplicate start and Temporal
retention expiry. Ambiguity about whether a start happened fails closed (no new start without
operator review).
Source §2, §5 week 8. Layer runtime. Enforced by outbox state machine + PostgreSQL action record
(ADR source of truth). Checked by planned (week 8). Lab signal: duplicate effects. Status: planned.

### Admission

**INV-08 — Same key, same action.**
Within a tenant, a request key maps to at most one action. The same key with a different canonical
payload hash is a deterministic conflict. Admission, idempotency record and outbox entry commit in
one transaction; concurrent duplicates resolve to the same action or the same conflict.
Source §2, §5 week 7. Layer runtime (DB constraints). Checked by planned (week 7).
Status: planned.

### Authorization and approval

**INV-09 — Authorize immediately before dispatch.**
No managed dispatch without authentication and authorization of the principal for the tenant,
resource and action, re-checked against current policy immediately before dispatch using trusted
facts only. Limits after dispatch (TOCTOU, revocation) are documented, not hidden.
Source §3, §11 ("unauthorized managed dispatch"). Layer runtime. Checked by planned (weeks 6, 10,
21 — every entry point). Status: planned.

**INV-10 — Approvals are bound to scope, versions and time.**
An approval permits dispatch only if its digest equals the canonical immutable action scope hash,
the action definition/implementation and policy versions match, and it is unexpired and unrevoked
at dispatch time.
Source §3, §5 week 10. Layer core (binding check) + runtime. Checked by planned (week 10).
Status: planned.

**INV-11 — No self-approval.**
The approving principal is not part of the requesting delegation chain, and approvals are accepted
only through the management interface, never through agent-facing interfaces (SDK, REST agent API,
MCP).
Source §5 weeks 10, 21. Layer runtime. Checked by planned (weeks 10, 21). Status: planned.

**INV-12 — Advisory facts never grant access or prove outcomes.**
Facts from untrusted sources (agent claims, request metadata, payload fields, embeddings) can at
most block or request review; they never authorize, attribute, merge intents or verify.
Source §2, §3. Layer core + runtime. Checked by planned (weeks 10, 13, 14, 16). Status: planned.

**INV-13 — Target credentials never reach agents.**
Target credentials exist only in worker processes; no agent-facing response, error, log, trace or
evidence record contains them.
Source §2, §11. Layer runtime. Checked by planned (weeks 6, 23 security tests). Status: planned.

### Tenancy

**INV-14 — Tenant isolation.**
No read, write, list, conflict response, error message or timing-independent signal reveals or
affects another tenant's actions, intents, resources, approvals or evidence.
Source §3, §11 ("broken resource isolation"). Layer runtime (repository + RLS, ADR week 6).
Checked by planned (weeks 7, 15 cross-tenant tests). Status: planned.

### Coordination

**INV-15 — No conflicting managed write during uncertainty.**
While an action on canonical resource key R is unresolved, no other managed conflicting write to R
is dispatched unless an authorized, audited risk-release is recorded. Reservation is acquired
atomically before dispatch. Fencing counts as protection only where the target or a trusted
boundary enforces it; a generated token alone is not protection. This does not protect against
writers outside Actraforge.
Source §2, §3. Layer core (conflict rules) + runtime (atomic reservation). Checked by planned
(week 12). Lab signal: duplicate/conflicting effects. Status: planned.

**INV-16 — Release does not change outcome.**
Quarantine release or risk-release changes coordination state only; the action's outcome,
resolution and evidence are unchanged.
Source §3. Layer core. Checked by planned (week 12). Status: planned.

**INV-17 — Projections never authorize.**
Authorization, reservation, release and dispatch decisions read authoritative state (PostgreSQL
coordination records or the workflow itself), never the sequence-versioned ledger projection. A
stale projection may only be displayed, marked as stale.
Source §2. Layer runtime (separate types for projection vs authoritative state). Checked by planned
(week 8). Status: planned.

### Cancellation and operations

**INV-18 — Cancellation after possible dispatch does not imply no effect.**
Cancellation before dispatch prevents the write. Cancellation after a possible dispatch is
recorded as such, never reported as "no effect", keeps the resource reservation until the outcome
is resolved, and does not stop reconciliation.
Source §3, §5 week 11. Layer core + runtime. Checked by planned (week 11). Lab signal: false
failure / duplicate effect after cancel. Status: planned.

**INV-19 — Every operator override is attributed and audited.**
Every approval, reconciliation verdict, release, risk-release and attestation records the
operator principal, time, reason and the exact state it applied to; there is no unaudited path.
Source §11 ("untraceable operator override"). Layer runtime. Checked by planned (weeks 12, 21).
Status: planned.

**INV-20 — The core is deterministic and free of I/O.**
Domain decisions are pure functions of their inputs: no I/O, clock reads, randomness, environment
access or hidden global state; the same inputs always give the same decision and reason code.
Source §2 ("Pure Core"). Layer core. Enforced by `tests/unit/test_domain_purity.py` (AST
allowlist) and property tests. Status: enforced (for current modules).

---

## 2. Intent identity (INV-I1 … INV-I5) — weeks 14–15

**INV-I1 — Links only through trusted identity.** Different request keys are linked to the same
intent only through an authorized stable intent handle or an author-defined, versioned fingerprint
match; never through embeddings, similarity or untrusted claims.

**INV-I2 — Ambiguity is a conflict, not a merge.** A fingerprint match with an unresolved action
and no explicit authorized link yields a conflict; the system never silently treats two requests as
one action.

**INV-I3 — Intent scope.** Fingerprint matching happens only inside the declared scope (tenant,
and principal/resource where declared); never across tenants, and conflict responses do not
disclose other scopes (with INV-14).

**INV-I4 — Legitimate second effects remain possible.** After the earlier action is resolved, a
fresh intent with an identical effect is admitted or rejected by explicit policy; a fingerprint
match never claims that two intentions are identical.

**INV-I5 — Intent handles cannot be hijacked.** A principal can attach a request only to intents
it is authorized for; a spoofed or foreign handle is rejected without disclosing its existence.

## 3. Delivery (INV-D1 … INV-D4) — week 17

**INV-D1 — Delivery is not outcome.** Delivery status (queued, acknowledged, pending, expired) is
a separate axis; no delivery state implies applied or verified.

**INV-D2 — A possibly pending command blocks conflicting writes.** While an earlier command may
still be queued or pending at the target, a new conflicting write is not dispatched (INV-15), unless
an authorized risk-release exists.

**INV-D3 — Expiry alone does not prove non-execution.** Command expiry establishes
`CONFIRMED_NOT_APPLIED` only together with the evidence required by `RECOVERY_DECISION_TABLE.md`
§3 item 3.

**INV-D4 — Late effects become new assessments.** An effect or evidence arriving after resolution
creates a new (possibly disputed) assessment (INV-03); it is never dropped and never rewrites history.

## 4. Attribution (INV-A1 … INV-A3) — week 16

**INV-A1 — Attribution needs a trusted linkage.** "Caused by this action/attempt" is claimed only
when a trusted target mechanism links the effect to our operation identity (target-echoed operation
ID, trusted event correlation); metadata copied into untrusted payloads never attributes.

**INV-A2 — Pre-existing goals are never attributed.** `ALREADY_SATISFIED` never carries
attribution to the current action (with INV-02).

**INV-A3 — Missing attribution is explicit.** When the target cannot provide linkage, the result
states "goal satisfied, attribution unknown"; the limitation is recorded with the action
definition.

## 5. Lab (INV-L1 … INV-L3) — weeks 4–5, 22

**INV-L1 — Runtime learns target reality only through adapters.** `src/actraforge` never imports
`lab`; enforced by an architecture test (week 4).

**INV-L2 — Independent ground truth.** Lab evaluators compute metrics from simulator ground truth,
never from runtime records or runtime-reported outcomes.

**INV-L3 — Reproducibility.** The same seed, scenario, versions and configuration produce the same
trace and metrics; every published result includes them.

## 6. Coverage summary

| Status | Invariants |
|---|---|
| enforced | INV-20 |
| partial | INV-04, INV-05 (core decision enforced; runtime gating planned) |
| planned | all others |

Update this table and each invariant's status whenever enforcement or tests land. A change that
weakens an invariant requires a contract revision recorded here, never a silent code change.
