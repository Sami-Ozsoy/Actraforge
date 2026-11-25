"""Properties of the pure recovery rule."""

from dataclasses import FrozenInstanceError, fields

import pytest
from hypothesis import given
from hypothesis import strategies as st

from actraforge.domain import (
    AttemptOutcome,
    DecisionKind,
    IdempotencyWindow,
    RecoveryContext,
    RetrySafety,
    WriteHistoryOutcome,
    decide_after_attempt,
    summarize_write_history,
)

ATTEMPTS = st.lists(st.sampled_from(AttemptOutcome), max_size=8)
CONTEXTS = st.builds(
    RecoveryContext,
    write_history=st.sampled_from(WriteHistoryOutcome),
    retry_safety=st.sampled_from(RetrySafety),
    idempotency_window=st.sampled_from(IdempotencyWindow),
)


@given(CONTEXTS)
def test_decision_is_deterministic(context: RecoveryContext) -> None:
    assert decide_after_attempt(context) == decide_after_attempt(context)


@given(CONTEXTS)
def test_context_and_decision_are_immutable(context: RecoveryContext) -> None:
    decision = decide_after_attempt(context)
    for value in (context, decision):
        for field in fields(value):
            with pytest.raises((FrozenInstanceError, AttributeError)):
                setattr(value, field.name, None)


@given(
    retry_safety=st.sampled_from(RetrySafety),
    window=st.sampled_from(IdempotencyWindow),
)
def test_unknown_permits_write_only_in_row_5(
    retry_safety: RetrySafety, window: IdempotencyWindow
) -> None:
    decision = decide_after_attempt(
        RecoveryContext(WriteHistoryOutcome.UNKNOWN, retry_safety, window)
    )
    assert decision.permits_write == (
        retry_safety is RetrySafety.IDEMPOTENT_WITH_KEY and window is IdempotencyWindow.OPEN
    )


@given(ATTEMPTS, st.sampled_from(RetrySafety), st.sampled_from(IdempotencyWindow))
def test_inv_r7_dispatch_requires_entirely_unsent_history(
    attempts: list[AttemptOutcome], safety: RetrySafety, window: IdempotencyWindow
) -> None:
    decision = decide_after_attempt(
        RecoveryContext(summarize_write_history(attempts), safety, window)
    )
    if decision.kind is DecisionKind.DISPATCH:
        assert all(attempt is AttemptOutcome.NOT_DISPATCHED for attempt in attempts)


@given(ATTEMPTS, ATTEMPTS)
def test_inv_r8_appending_attempts_preserves_prior_dispatch_and_uncertainty(
    history: list[AttemptOutcome], suffix: list[AttemptOutcome]
) -> None:
    summary = summarize_write_history(history + suffix)
    if any(attempt is not AttemptOutcome.NOT_DISPATCHED for attempt in history):
        assert summary is not WriteHistoryOutcome.NO_WRITE_DISPATCHED
    if AttemptOutcome.UNKNOWN in history:
        assert summary is not WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED


@given(ATTEMPTS, st.data())
def test_inv_r9_history_summary_is_order_independent(
    attempts: list[AttemptOutcome], data: st.DataObject
) -> None:
    reordered = data.draw(st.permutations(attempts))
    assert summarize_write_history(attempts) is summarize_write_history(reordered)
