"""Check recovery decisions against the table published in the contract."""

from enum import StrEnum
from itertools import product
from pathlib import Path

import pytest

from actraforge.domain import (
    DecisionKind,
    IdempotencyWindow,
    ReasonCode,
    RecoveryContext,
    RetrySafety,
    WriteHistoryOutcome,
    decide_after_attempt,
)

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "contracts" / "RECOVERY_DECISION_TABLE.md"
)

type RecoveryInputs = tuple[WriteHistoryOutcome, RetrySafety, IdempotencyWindow]
type ExpectedDecision = tuple[DecisionKind, ReasonCode]


def _parse_members[Member: StrEnum](cell: str, enum_type: type[Member]) -> tuple[Member, ...]:
    if cell == "*":
        return tuple(enum_type)

    members = []
    for alternative in cell.split(","):
        token = alternative.strip()
        if len(token) < 3 or not (token.startswith("`") and token.endswith("`")):
            raise ValueError(f"Expected a backticked {enum_type.__name__} member, got {token!r}")
        name = token[1:-1]
        try:
            members.append(enum_type[name])
        except KeyError as error:
            raise ValueError(f"Unknown {enum_type.__name__} member {name!r}") from error
    return tuple(members)


def _parse_contract_table(source: str) -> tuple[int, dict[RecoveryInputs, ExpectedDecision]]:
    lines = iter(source.splitlines())
    for line in lines:
        if line.startswith("| # | Write history |"):
            break
    else:
        raise ValueError("Recovery decision table header is missing")

    if not next(lines, "").startswith("|---"):
        raise ValueError("Recovery decision table separator is missing")

    row_count = 0
    expected: dict[RecoveryInputs, ExpectedDecision] = {}
    for line in lines:
        if not line.startswith("|"):
            break
        _, history_cell, safety_cell, window_cell, kind_cell, reason_cell = (
            cell.strip() for cell in line.split("|")[1:-1]
        )
        histories = _parse_members(history_cell, WriteHistoryOutcome)
        policies = _parse_members(safety_cell, RetrySafety)
        windows = _parse_members(window_cell, IdempotencyWindow)
        (kind,) = _parse_members(kind_cell, DecisionKind)
        (reason,) = _parse_members(reason_cell, ReasonCode)
        for inputs in product(histories, policies, windows):
            expected.setdefault(inputs, (kind, reason))
        row_count += 1
    return row_count, expected


def test_decisions_match_the_published_contract_table() -> None:
    row_count, expected = _parse_contract_table(CONTRACT_PATH.read_text(encoding="utf-8"))
    inputs = set(product(WriteHistoryOutcome, RetrySafety, IdempotencyWindow))
    assert row_count == 8
    assert len(expected) == len(inputs) == 48
    assert expected.keys() == inputs
    for context, (kind, reason) in expected.items():
        decision = decide_after_attempt(RecoveryContext(*context))
        assert decision.kind is kind, context
        assert decision.reason is reason, context


def test_contract_table_parser_rejects_unknown_enum_member() -> None:
    source = (
        "| # | Write history | Retry safety | Window | Decision | Reason code |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | `UNKNOWN_MEMBER` | * | * | `DISPATCH` | `NO_PRIOR_DISPATCH` |\n"
    )
    with pytest.raises(ValueError, match=r"^Unknown WriteHistoryOutcome member 'UNKNOWN_MEMBER'$"):
        _parse_contract_table(source)
