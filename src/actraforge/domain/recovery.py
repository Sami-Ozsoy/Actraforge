"""Decide what may follow a write attempt using the action's history and retry policy."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never


class RetrySafety(StrEnum):
    """Retry capability declared by the trusted action author."""

    # The target deduplicates by key within a bounded window. Safe retries require the same key
    # and canonical request while the window is known to be open.
    IDEMPOTENT_WITH_KEY = "IDEMPOTENT_WITH_KEY"
    # Without target deduplication, trusted evidence must rule out past and future application
    # of every earlier attempt before another write.
    RECONCILE_FIRST = "RECONCILE_FIRST"
    # Once any write has been dispatched, the action forbids further writes.
    NEVER_RETRY = "NEVER_RETRY"


class AttemptOutcome(StrEnum):
    """What the dispatch guard or effect evidence establishes about the attempt."""

    # The durable dispatch guard proves this request was never sent. A crash after the dispatch
    # intent was recorded leaves the outcome unknown.
    NOT_DISPATCHED = "NOT_DISPATCHED"
    # Trusted evidence establishes that the attempt took effect. Verify the goal separately.
    CONFIRMED_APPLIED = "CONFIRMED_APPLIED"
    # Trusted evidence meeting the contract's criteria proves the attempt did not apply and
    # cannot apply later.
    CONFIRMED_NOT_APPLIED = "CONFIRMED_NOT_APPLIED"
    # The effect is unresolved, including timeouts, lost responses, connection resets, crashes
    # after dispatch, acknowledgements without effect evidence, and inconclusive errors.
    UNKNOWN = "UNKNOWN"


class WriteHistoryOutcome(StrEnum):
    """Summary of the current assessments of every write attempt for an action."""

    # No attempt was ever sent, including when the history is empty.
    NO_WRITE_DISPATCHED = "NO_WRITE_DISPATCHED"
    # Trusted evidence confirms at least one attempt took effect.
    CONFIRMED_APPLIED = "CONFIRMED_APPLIED"
    # At least one attempt was sent, and every sent attempt provably did not and cannot apply.
    ALL_CONFIRMED_NOT_APPLIED = "ALL_CONFIRMED_NOT_APPLIED"
    # At least one attempt is unresolved, and no attempt is confirmed applied.
    UNKNOWN = "UNKNOWN"


class IdempotencyWindow(StrEnum):
    """Known state of the target's deduplication window for the operation key."""

    # Known to stay open until the retry reaches the target. Measure from the key's earliest
    # dispatch and subtract a margin for clock skew and maximum dispatch latency.
    OPEN = "OPEN"
    # The window is known to have expired.
    CLOSED = "CLOSED"
    # The window state cannot be established.
    UNKNOWN = "UNKNOWN"
    # The operation has no key or window.
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DecisionKind(StrEnum):
    """Next action selected by the recovery table."""

    # Proceed with the first send because no write for this action was ever sent.
    DISPATCH = "DISPATCH"
    # Stop writing and verify the goal through trusted evidence.
    PROCEED_TO_VERIFY = "PROCEED_TO_VERIFY"
    # Resend with the identical key and canonical request (same payload hash). Re-check the
    # window deadline immediately before sending and abort if it has passed.
    RETRY_SAME_OPERATION_KEY = "RETRY_SAME_OPERATION_KEY"
    # Start a new attempt because every earlier dispatched attempt provably cannot apply.
    # The action author declares the key choice, which does not affect safety here.
    NEW_ATTEMPT = "NEW_ATTEMPT"
    # Establish the earlier attempts' outcomes without writing.
    RECONCILE = "RECONCILE"
    # End write attempts for the action.
    STOP = "STOP"


class ReasonCode(StrEnum):
    """Machine-readable explanation identifying the selected recovery row."""

    # The history contains no prior send for this action.
    NO_PRIOR_DISPATCH = "NO_PRIOR_DISPATCH"
    # Trusted evidence confirmed an attempt applied.
    ATTEMPT_CONFIRMED_APPLIED = "ATTEMPT_CONFIRMED_APPLIED"
    # Earlier writes cannot apply, and policy forbids another attempt.
    NEVER_RETRY_POLICY = "NEVER_RETRY_POLICY"
    # Earlier writes cannot apply, and policy permits another attempt.
    ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED = "ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED"
    # The unknown history permits retry with the same key and request inside the open window.
    UNKNOWN_IDEMPOTENCY_WINDOW_OPEN = "UNKNOWN_IDEMPOTENCY_WINDOW_OPEN"
    # The unknown outcome requires reconciliation because an open window is unproven.
    UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED = "UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED"
    # The policy requires reconciliation of the unknown outcome before any further write.
    UNKNOWN_RECONCILE_FIRST = "UNKNOWN_RECONCILE_FIRST"
    # Reconcile to learn the unknown outcome under a policy that forbids further writes.
    UNKNOWN_NEVER_RETRY = "UNKNOWN_NEVER_RETRY"


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    """Facts supplied to the recovery decision table."""

    write_history: WriteHistoryOutcome
    retry_safety: RetrySafety
    idempotency_window: IdempotencyWindow

    def __post_init__(self) -> None:
        """Require the exact enum type for every recovery input."""
        if type(self.write_history) is not WriteHistoryOutcome:
            raise TypeError("write_history must be a WriteHistoryOutcome")
        if type(self.retry_safety) is not RetrySafety:
            raise TypeError("retry_safety must be a RetrySafety")
        if type(self.idempotency_window) is not IdempotencyWindow:
            raise TypeError("idempotency_window must be an IdempotencyWindow")


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    """Selected recovery action and the reason for selecting it."""

    kind: DecisionKind
    reason: ReasonCode

    @property
    def permits_write(self) -> bool:
        """Return whether this decision authorizes a write attempt."""
        match self.kind:
            case (
                DecisionKind.DISPATCH
                | DecisionKind.RETRY_SAME_OPERATION_KEY
                | DecisionKind.NEW_ATTEMPT
            ):
                return True
            case DecisionKind.PROCEED_TO_VERIFY | DecisionKind.RECONCILE | DecisionKind.STOP:
                return False
        assert_never(self.kind)


def summarize_write_history(attempts: Sequence[AttemptOutcome]) -> WriteHistoryOutcome:
    """Validate and summarize all attempts in contract precedence order."""
    outcomes: set[AttemptOutcome] = set()
    for attempt in attempts:
        if type(attempt) is not AttemptOutcome:
            raise TypeError("every attempt must be an AttemptOutcome")
        outcomes.add(attempt)

    if AttemptOutcome.CONFIRMED_APPLIED in outcomes:
        return WriteHistoryOutcome.CONFIRMED_APPLIED
    if AttemptOutcome.UNKNOWN in outcomes:
        return WriteHistoryOutcome.UNKNOWN
    if AttemptOutcome.CONFIRMED_NOT_APPLIED in outcomes:
        return WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED
    return WriteHistoryOutcome.NO_WRITE_DISPATCHED


def decide_after_attempt(context: RecoveryContext) -> RecoveryDecision:
    """Select the first matching recovery row for the action's write history."""
    match context.write_history:
        case WriteHistoryOutcome.NO_WRITE_DISPATCHED:
            return RecoveryDecision(DecisionKind.DISPATCH, ReasonCode.NO_PRIOR_DISPATCH)
        case WriteHistoryOutcome.CONFIRMED_APPLIED:
            return RecoveryDecision(
                DecisionKind.PROCEED_TO_VERIFY, ReasonCode.ATTEMPT_CONFIRMED_APPLIED
            )
        case WriteHistoryOutcome.ALL_CONFIRMED_NOT_APPLIED:
            match context.retry_safety:
                case RetrySafety.NEVER_RETRY:
                    return RecoveryDecision(DecisionKind.STOP, ReasonCode.NEVER_RETRY_POLICY)
                case RetrySafety.IDEMPOTENT_WITH_KEY | RetrySafety.RECONCILE_FIRST:
                    return RecoveryDecision(
                        DecisionKind.NEW_ATTEMPT,
                        ReasonCode.ALL_CONFIRMED_NOT_APPLIED_RETRY_PERMITTED,
                    )
            assert_never(context.retry_safety)
        case WriteHistoryOutcome.UNKNOWN:
            match context.retry_safety:
                case RetrySafety.IDEMPOTENT_WITH_KEY:
                    match context.idempotency_window:
                        case IdempotencyWindow.OPEN:
                            return RecoveryDecision(
                                DecisionKind.RETRY_SAME_OPERATION_KEY,
                                ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_OPEN,
                            )
                        case (
                            IdempotencyWindow.CLOSED
                            | IdempotencyWindow.UNKNOWN
                            | IdempotencyWindow.NOT_APPLICABLE
                        ):
                            return RecoveryDecision(
                                DecisionKind.RECONCILE,
                                ReasonCode.UNKNOWN_IDEMPOTENCY_WINDOW_NOT_ESTABLISHED,
                            )
                    assert_never(context.idempotency_window)
                case RetrySafety.RECONCILE_FIRST:
                    return RecoveryDecision(
                        DecisionKind.RECONCILE, ReasonCode.UNKNOWN_RECONCILE_FIRST
                    )
                case RetrySafety.NEVER_RETRY:
                    return RecoveryDecision(DecisionKind.RECONCILE, ReasonCode.UNKNOWN_NEVER_RETRY)
            assert_never(context.retry_safety)
    assert_never(context.write_history)
