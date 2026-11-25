"""Pure domain types and recovery decisions."""

from .recovery import (
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

__all__ = [
    "AttemptOutcome",
    "DecisionKind",
    "IdempotencyWindow",
    "ReasonCode",
    "RecoveryContext",
    "RecoveryDecision",
    "RetrySafety",
    "WriteHistoryOutcome",
    "decide_after_attempt",
    "summarize_write_history",
]
