"""Check each recovery row and the invariants over the complete input space."""

from itertools import product
from typing import cast

import pytest

from actraforge.domain import (
    AttemptOutcome,
    DecisionKind,
    IdempotencyWindow,
    ReasonCode,
    RecoveryContext,
    RecoveryDecision,
    RetrySafety,
    WriteHistoryOutcome,
    decide_after_attempt,
    summarize_write_history,
)

INPUTS = tuple(product(WriteHistoryOutcome, RetrySafety, IdempotencyWindow))


def test_row_1_dispatches_a_guard_proven_unsent_request() -> None:
    decision = decide_after_attempt(
        RecoveryContext(
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.NOT_APPLICABLE,
        )
    )
    assert decision.kind is DecisionKind.DISPATCH
    assert decision.reason is ReasonCode.NO_PRIOR_DISPATCH


def test_row_2_verifies_a_confirmed_applied_attempt() -> None:
    decision = decide_after_attempt(
        RecoveryContext(
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.NOT_APPLICABLE,
        )
    )
    assert decision.kind is DecisionKind.PROCEED_TO_VERIFY
    assert decision.reason is ReasonCode.ATTEMPT_CONFIRMED_APPLIED


def test_row_3_stops_under_never_retry() -> None:
    decision = decide_after_attempt(
        RecoveryContext(
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.OPEN,
        )
    )
    assert decision.kind is DecisionKind.STOP
    assert decision.reason is ReasonCode.NEVER_RETRY_POLICY


def test_row_4_allows_a_new_attempt_after_confirmed_non_application() -> None:
    decision = decide_after_attempt(
        RecoveryContext(
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.NOT_APPLICABLE,
        )
    )
    assert decision.kind is DecisionKind.NEW_ATTEMPT
    assert decision.reason is ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED


def test_row_5_reuses_the_key_inside_an_open_window() -> None:
    decision = decide_after_attempt(
        RecoveryContext(
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.OPEN,
        )
    )
    assert decision.kind is DecisionKind.RETRY_SAME_OPERATION_KEY
    assert decision.reason is ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_OPEN


def test_row_6_reconciles_without_an_established_open_window() -> None:
    decision = decide_after_attempt(
        RecoveryContext(
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.NOT_APPLICABLE,
        )
    )
    assert decision.kind is DecisionKind.RECONCILE
    assert decision.reason is ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED


def test_row_7_reconciles_under_reconcile_first() -> None:
    decision = decide_after_attempt(
        RecoveryContext(
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.OPEN,
        )
    )
    assert decision.kind is DecisionKind.RECONCILE
    assert decision.reason is ReasonCode.UNKNOWN_RECONCILE_FIRST


def test_row_8_reconciles_under_never_retry() -> None:
    decision = decide_after_attempt(
        RecoveryContext(
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.OPEN,
        )
    )
    assert decision.kind is DecisionKind.RECONCILE
    assert decision.reason is ReasonCode.UNKNOWN_NEVER_RETRY


def test_inv_r1_unknown_never_new_attempt_or_dispatch() -> None:
    for history, safety, window in INPUTS:
        if history is WriteHistoryOutcome.UNKNOWN:
            decision = decide_after_attempt(RecoveryContext(history, safety, window))
            assert decision.kind not in {DecisionKind.NEW_ATTEMPT, DecisionKind.DISPATCH}


def test_inv_r2_same_key_retry_requires_unknown_outcome_and_open_window() -> None:
    for history, safety, window in INPUTS:
        decision = decide_after_attempt(RecoveryContext(history, safety, window))
        if decision.kind is DecisionKind.RETRY_SAME_OPERATION_KEY:
            assert history is WriteHistoryOutcome.UNKNOWN
            assert safety is RetrySafety.IDEMPOTENT_WITH_KEY
            assert window is IdempotencyWindow.OPEN


def test_inv_r3_never_retry_disallows_retry_after_dispatch() -> None:
    for history, safety, window in INPUTS:
        if safety is RetrySafety.NEVER_RETRY:
            decision = decide_after_attempt(RecoveryContext(history, safety, window))
            assert decision.kind not in {
                DecisionKind.NEW_ATTEMPT,
                DecisionKind.RETRY_SAME_OPERATION_KEY,
            }


def test_inv_r4_confirmed_applied_never_permits_write() -> None:
    for history, safety, window in INPUTS:
        if history is WriteHistoryOutcome.CONFIRMED_APPLIED:
            decision = decide_after_attempt(RecoveryContext(history, safety, window))
            assert not decision.permits_write


def test_inv_r5_new_attempt_requires_confirmed_non_application() -> None:
    for history, safety, window in INPUTS:
        decision = decide_after_attempt(RecoveryContext(history, safety, window))
        if decision.kind is DecisionKind.NEW_ATTEMPT:
            assert history is WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED


def test_inv_r6_matches_expected_table_for_every_input() -> None:
    expected = {
        # NO_WRITE_DISPATCHED
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        (
            WriteHistoryOutcome.NO_WRITE_DISPATCHED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.DISPATCH,
            ReasonCode.NO_PRIOR_DISPATCH,
        ),
        # CONFIRMED_APPLIED
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        (
            WriteHistoryOutcome.CONFIRMED_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.PROCEED_TO_VERIFY,
            ReasonCode.ATTEMPT_CONFIRMED_APPLIED,
        ),
        # ALL_CONFIRMED_NOT_APPLIED
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.NEW_ATTEMPT,
            ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.NEW_ATTEMPT,
            ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.NEW_ATTEMPT,
            ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.NEW_ATTEMPT,
            ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.NEW_ATTEMPT,
            ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.NEW_ATTEMPT,
            ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.NEW_ATTEMPT,
            ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.NEW_ATTEMPT,
            ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.STOP,
            ReasonCode.NEVER_RETRY_POLICY,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.STOP,
            ReasonCode.NEVER_RETRY_POLICY,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.STOP,
            ReasonCode.NEVER_RETRY_POLICY,
        ),
        (
            WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.STOP,
            ReasonCode.NEVER_RETRY_POLICY,
        ),
        # UNKNOWN
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.RETRY_SAME_OPERATION_KEY,
            ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_OPEN,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_RECONCILE_FIRST,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_RECONCILE_FIRST,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_RECONCILE_FIRST,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.RECONCILE_FIRST,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_RECONCILE_FIRST,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.OPEN,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_NEVER_RETRY,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.CLOSED,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_NEVER_RETRY,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.UNKNOWN,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_NEVER_RETRY,
        ),
        (
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.NEVER_RETRY,
            IdempotencyWindow.NOT_APPLICABLE,
        ): (
            DecisionKind.RECONCILE,
            ReasonCode.UNKNOWN_NEVER_RETRY,
        ),
    }
    assert len(expected) == len(INPUTS) == 48
    assert expected.keys() == set(INPUTS)
    assert {reason for _, reason in expected.values()} == set(ReasonCode)
    for inputs in INPUTS:
        decision = decide_after_attempt(RecoveryContext(*inputs))
        kind, reason = expected[inputs]
        assert decision.kind is kind, inputs
        assert decision.reason is reason, inputs


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (DecisionKind.DISPATCH, True),
        (DecisionKind.PROCEED_TO_VERIFY, False),
        (DecisionKind.RETRY_SAME_OPERATION_KEY, True),
        (DecisionKind.NEW_ATTEMPT, True),
        (DecisionKind.RECONCILE, False),
        (DecisionKind.STOP, False),
    ],
)
def test_permits_write_truth_table(kind: DecisionKind, expected: bool) -> None:
    assert RecoveryDecision(kind, ReasonCode.NO_PRIOR_DISPATCH).permits_write is expected


def test_h1_confirmed_application_takes_precedence() -> None:
    attempts = [
        AttemptOutcome.UNKNOWN,
        AttemptOutcome.CONFIRMED_APPLIED,
        AttemptOutcome.CONFIRMED_NOT_APPLIED,
    ]
    assert summarize_write_history(attempts) is WriteHistoryOutcome.CONFIRMED_APPLIED


def test_h2_unknown_takes_precedence_over_confirmed_non_application() -> None:
    attempts = [AttemptOutcome.CONFIRMED_NOT_APPLIED, AttemptOutcome.UNKNOWN]
    assert summarize_write_history(attempts) is WriteHistoryOutcome.UNKNOWN


def test_h3_all_dispatched_attempts_are_confirmed_not_applied() -> None:
    attempts = (AttemptOutcome.NOT_DISPATCHED, AttemptOutcome.CONFIRMED_NOT_APPLIED)
    assert summarize_write_history(attempts) is WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED


@pytest.mark.parametrize("attempts", [[], [AttemptOutcome.NOT_DISPATCHED] * 2])
def test_h4_empty_or_entirely_unsent_history(attempts: list[AttemptOutcome]) -> None:
    assert summarize_write_history(attempts) is WriteHistoryOutcome.NO_WRITE_DISPATCHED


def test_regression_b1_undispatched_retry_does_not_hide_unknown_attempt() -> None:
    history = summarize_write_history([AttemptOutcome.UNKNOWN, AttemptOutcome.NOT_DISPATCHED])
    assert history is WriteHistoryOutcome.UNKNOWN

    context = RecoveryContext(history, RetrySafety.IDEMPOTENT_WITH_KEY, IdempotencyWindow.CLOSED)
    decision = decide_after_attempt(context)
    assert decision.kind is DecisionKind.RECONCILE
    assert decision.reason is ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED
    assert not decision.permits_write


@pytest.mark.parametrize("safety", [RetrySafety.IDEMPOTENT_WITH_KEY, RetrySafety.RECONCILE_FIRST])
@pytest.mark.parametrize("window", list(IdempotencyWindow))
def test_regression_b2_later_rejection_does_not_clear_unknown_attempt(
    safety: RetrySafety, window: IdempotencyWindow
) -> None:
    history = summarize_write_history(
        [AttemptOutcome.UNKNOWN, AttemptOutcome.CONFIRMED_NOT_APPLIED]
    )
    assert history is WriteHistoryOutcome.UNKNOWN

    decision = decide_after_attempt(RecoveryContext(history, safety, window))
    assert decision.kind in {DecisionKind.RECONCILE, DecisionKind.RETRY_SAME_OPERATION_KEY}


@pytest.mark.parametrize(
    "value",
    ["UNKNOWN", IdempotencyWindow.UNKNOWN, AttemptOutcome.UNKNOWN],
    ids=["plain-string", "window-member", "attempt-member"],
)
def test_context_rejects_inexact_write_history_type(value: object) -> None:
    with pytest.raises(TypeError, match=r"^write_history must be a WriteHistoryOutcome$"):
        RecoveryContext(
            cast(WriteHistoryOutcome, value), RetrySafety.NEVER_RETRY, IdempotencyWindow.CLOSED
        )


def test_context_rejects_inexact_retry_safety_type() -> None:
    with pytest.raises(TypeError, match=r"^retry_safety must be a RetrySafety$"):
        RecoveryContext(
            WriteHistoryOutcome.UNKNOWN,
            cast(RetrySafety, "NEVER_RETRY"),
            IdempotencyWindow.CLOSED,
        )


def test_context_rejects_inexact_window_type() -> None:
    with pytest.raises(TypeError, match=r"^idempotency_window must be an IdempotencyWindow$"):
        RecoveryContext(
            WriteHistoryOutcome.UNKNOWN,
            RetrySafety.IDEMPOTENT_WITH_KEY,
            cast(IdempotencyWindow, WriteHistoryOutcome.UNKNOWN),
        )


@pytest.mark.parametrize(
    "values",
    [["UNKNOWN"], [WriteHistoryOutcome.UNKNOWN], [AttemptOutcome.CONFIRMED_APPLIED, "UNKNOWN"]],
    ids=["plain-string", "history-member", "invalid-after-confirmed-application"],
)
def test_history_rejects_inexact_attempt_type(values: list[object]) -> None:
    with pytest.raises(TypeError, match=r"^every attempt must be an AttemptOutcome$"):
        summarize_write_history(cast(list[AttemptOutcome], values))
