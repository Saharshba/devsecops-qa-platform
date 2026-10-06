"""Unit tests for the issue state machine.

Pure functions, no database: these are the rules the API defers to, so they are
tested exhaustively here rather than through HTTP.
"""

from __future__ import annotations

import pytest

from app.models import IssueStatus, Priority, Role
from app.services.workflow import (
    TRANSITIONS,
    TransitionError,
    allowed_targets,
    check_transition,
    is_terminal,
    issue_key,
    validate_transition,
)

S = IssueStatus


def test_every_status_has_an_exit():
    """No status may be a dead end — including CLOSED, which reopens."""
    for status in S:
        assert allowed_targets(status), f"{status.value} has no outgoing transition"


@pytest.mark.parametrize(
    "current,target",
    [
        (S.OPEN, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.IN_REVIEW),
        (S.IN_REVIEW, S.DONE),
        (S.IN_PROGRESS, S.OPEN),
        (S.IN_REVIEW, S.IN_PROGRESS),
        (S.DONE, S.IN_PROGRESS),
        (S.CLOSED, S.OPEN),
    ],
)
def test_permitted_moves(current, target):
    assert check_transition(current, target, role=Role.MANAGER).allowed


@pytest.mark.parametrize(
    "current,target",
    [
        (S.OPEN, S.DONE),  # work cannot skip review
        (S.OPEN, S.IN_REVIEW),
        (S.DONE, S.OPEN),  # reopen goes through IN_PROGRESS
        (S.CLOSED, S.DONE),
        (S.CLOSED, S.IN_PROGRESS),
    ],
)
def test_forbidden_moves(current, target):
    check = check_transition(current, target, role=Role.ADMIN)
    assert not check.allowed
    assert "Cannot move" in check.reason


def test_a_no_op_transition_is_rejected():
    check = check_transition(S.OPEN, S.OPEN, role=Role.ADMIN)
    assert not check.allowed
    assert "already" in check.reason


def test_viewers_cannot_move_issues():
    check = check_transition(S.OPEN, S.IN_PROGRESS, role=Role.VIEWER)
    assert not check.allowed
    assert "VIEWER" in check.reason


def test_only_managers_and_admins_close_issues():
    assert not check_transition(S.OPEN, S.CLOSED, role=Role.DEVELOPER).allowed
    assert check_transition(S.OPEN, S.CLOSED, role=Role.MANAGER).allowed
    assert check_transition(S.OPEN, S.CLOSED, role=Role.ADMIN).allowed


def test_work_cannot_start_on_an_unassigned_issue():
    check = check_transition(S.OPEN, S.IN_PROGRESS, role=Role.DEVELOPER, has_assignee=False)
    assert not check.allowed
    assert "Assign the issue" in check.reason


def test_a_developer_may_start_work_they_are_assigned():
    assert check_transition(S.OPEN, S.IN_PROGRESS, role=Role.DEVELOPER, has_assignee=False, is_assignee=True).allowed


def test_the_assignee_cannot_mark_their_own_work_done():
    check = check_transition(S.IN_REVIEW, S.DONE, role=Role.DEVELOPER, is_assignee=True)
    assert not check.allowed
    assert "own issue" in check.reason
    # …but another developer reviewing it can.
    assert check_transition(S.IN_REVIEW, S.DONE, role=Role.DEVELOPER, is_assignee=False).allowed
    # …and so can a manager.
    assert check_transition(S.IN_REVIEW, S.DONE, role=Role.MANAGER, is_assignee=True).allowed


def test_validate_transition_raises_with_the_reason():
    with pytest.raises(TransitionError, match="Cannot move"):
        validate_transition(S.OPEN, S.DONE, role=Role.ADMIN)


def test_terminal_statuses():
    assert is_terminal(S.DONE) and is_terminal(S.CLOSED)
    assert not is_terminal(S.OPEN) and not is_terminal(S.IN_REVIEW)


def test_transition_table_has_no_self_loops():
    for status, targets in TRANSITIONS.items():
        assert status not in targets


@pytest.mark.parametrize("key,number,expected", [("pay", 1, "PAY-1"), ("PAY", 42, "PAY-42"), ("ab1", 7, "AB1-7")])
def test_issue_key_formatting(key, number, expected):
    assert issue_key(key, number) == expected


def test_priority_sorting_puts_critical_first():
    from dataclasses import dataclass
    from datetime import datetime

    from app.services.workflow import sort_key

    @dataclass
    class Fake:
        priority: Priority
        created_at: datetime

    now = datetime(2026, 1, 1)
    issues = [
        Fake(Priority.LOW, now),
        Fake(Priority.CRITICAL, now),
        Fake(Priority.MEDIUM, now),
        Fake(Priority.HIGH, now),
    ]
    assert [i.priority for i in sorted(issues, key=sort_key)] == [
        Priority.CRITICAL,
        Priority.HIGH,
        Priority.MEDIUM,
        Priority.LOW,
    ]
