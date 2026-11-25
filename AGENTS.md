# AGENTS.md — rules for coding agents working on Actraforge

Read this file completely before changing anything. The planning documents are
`Actraforge_ROADMAP.md` (scope and schedule) and `Actraforge_RISKS.md` (risks and open decisions).
Contracts live in `docs/contracts/`, architecture decisions in `docs/adr/`.

## 1. What this project is

Actraforge is an open-source runtime and test lab for **reliable external actions** taken by
(possibly unreliable) agents over unreliable networks. Correctness never depends on an LLM.
The core value is *safety semantics*, not features. When in doubt, choose the behaviour that
cannot produce a duplicate external effect or a false success.

## 2. Non-negotiable safety rules

These rules override convenience, performance and test-passing. Never weaken them to make a test
pass; report the conflict instead.

1. A timeout, lost response or crash after dispatch is **not** proof of non-execution. The outcome
   is `UNKNOWN`.
2. No write retry unless safety is established: idempotent retries must reuse the same target
   operation key inside its enforced window; `RECONCILE_FIRST` requires trusted evidence that the
   old command did not and cannot later apply; `NEVER_RETRY` forbids further write attempts.
3. Unknown or disputed evidence is never machine-verified success. An acknowledgement (ACK) is not
   success. `ALREADY_SATISFIED` is not proof that we executed anything.
4. Unsafe default is denied: any input combination not explicitly allowed must resolve to a
   non-writing decision (reconcile or stop).
5. No hidden retries for writes (HTTP client retries, Temporal activity retries > 1, SDK retries).
6. Terminal history is append-only; later contradictory evidence creates a disputed assessment,
   never a silent overwrite.
7. Advisory (untrusted) facts never grant access or prove outcomes.

## 3. Architecture rules

- `src/actraforge/domain/` is the **pure core**: deterministic, no I/O, no third-party imports.
  - Allowed imports: `__future__`, `abc`, `collections`, `collections.abc`, `dataclasses`,
    `datetime`, `decimal`, `enum`, `functools`, `itertools`, `re`, `types`, `typing`, and
    `actraforge.domain.*`. Nothing else. This is enforced by `tests/unit/test_domain_purity.py`.
  - No clock reads (`datetime.now`, `utcnow`, `today`, `time.*`), no randomness, no `uuid4`,
    no environment access, no logging. Time and identifiers are passed in as values.
  - Model with `@dataclass(frozen=True, slots=True)` and `enum.Enum`/`StrEnum`. Pydantic belongs
    at the interface/persistence boundaries, not in the domain.
- Layering (target, see roadmap §12): `domain` ← `application` ← `infrastructure` / `interfaces`.
  Inner layers never import outer layers.
- `lab/` (simulator, ground truth) must never be imported by `src/actraforge/`. The runtime may
  only learn target reality through an adapter.
- Decision functions are total over their finite input space and return a value with a
  machine-readable reason code. Use `match` with `typing.assert_never` for exhaustiveness.

## 4. Code style

- Python ≥ 3.12, fully typed, `mypy --strict` clean. No `Any` in the domain. No `# type: ignore`
  without a specific error code and a comment explaining why.
- `ruff check` and `ruff format` clean (configuration in `pyproject.toml`).
- No broad `except Exception` in the domain. No mutable default arguments. No global state.
- Public names get a one-line docstring stating the semantic, especially for enums whose
  members encode safety meaning.
- Do not add a dependency unless the task brief explicitly allows it. Declare dependencies in
  `pyproject.toml`; `uv.lock` is committed.

## 5. Tests

- Every decision rule has unit tests. Finite decision spaces are tested by **full enumeration**
  (`itertools.product` over all enum members) plus explicit invariant assertions.
- Property tests use Hypothesis. CI uses the `ci` profile (`derandomize=True`), selected with
  `HYPOTHESIS_PROFILE=ci`; profiles are registered in `tests/conftest.py`.
- Test layout: `tests/unit`, `tests/property`, later `tests/stateful`, `tests/integration`,
  `tests/security`, `tests/failure`.
- A test that encodes a safety rule names the rule in its name or docstring.

## 6. Verification commands

Run all of these before reporting completion; all must pass:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
HYPOTHESIS_PROFILE=ci uv run pytest
```

## 7. Working rules for agents

- Do **not** commit, push, create branches, tag or open PRs.
- Do **not** edit these controller-owned files unless the brief explicitly says so:
  `AGENTS.md`, `README.md`, `Actraforge_ROADMAP.md`, `Actraforge_RISKS.md`, `CLAUDE.local.md`,
  `LICENSE`, anything under `docs/`.
- If the brief conflicts with this file or with `docs/contracts/`, stop and report the conflict
  instead of choosing silently.
- Stay inside the scope of the brief. Note out-of-scope problems in the report instead of fixing
  them.

## 8. Report format

End every task with:

1. **Changed files** — path and one line each.
2. **Commands run** — each verification command and its result (pass/fail, counts).
3. **Decisions made** — anything not fully specified by the brief.
4. **Open issues** — anything left undone, uncertain or conflicting.
