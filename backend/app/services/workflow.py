"""The issue workflow.

A state machine, kept as pure functions so the rules can be tested without a
database. Everything that changes an issue's status goes through
`validate_transition`, so the API, the tests and any future importer all obey
the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import IssueStatus, Priority, Role

# Allowed moves. Deliberately not a free-for-all: work cannot jump from OPEN
# straight to DONE, and a CLOSED issue must be reopened before it moves again.
TRANSITIONS: dict[IssueStatus, set[IssueStatus]] = {
    IssueStatus.OPEN: {IssueStatus.IN_PROGRESS, IssueStatus.CLOSED},
    IssueStatus.IN_PROGRESS: {IssueStatus.IN_REVIEW, IssueStatus.OPEN, IssueStatus.CLOSED},
    IssueStatus.IN_REVIEW: {IssueStatus.DONE, IssueStatus.IN_PROGRESS, IssueStatus.CLOSED},
    IssueStatus.DONE: {IssueStatus.CLOSED, IssueStatus.IN_PROGRESS},
    IssueStatus.CLOSED: {IssueStatus.OPEN},
}

# Statuses that end the issue's active life; they stamp `closed_at`.
TERMINAL = {IssueStatus.DONE, IssueStatus.CLOSED}

# Moving an issue into review or done is a reviewer action; a VIEWER never
# changes state at all.
ROLES_THAT_MAY_TRANSITION = {Role.ADMIN, Role.MANAGER, Role.DEVELOPER}
ROLES_THAT_MAY_CLOSE = {Role.ADMIN, Role.MANAGER}

PRIORITY_ORDER = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


class TransitionError(ValueError):
    """Raised when a status change is not permitted."""


@dataclass(frozen=True)
class TransitionCheck:
    allowed: bool
    reason: str = ""


def allowed_targets(status: IssueStatus) -> set[IssueStatus]:
    return set(TRANSITIONS.get(status, set()))


def check_transition(
    current: IssueStatus,
    target: IssueStatus,
    *,
    role: Role,
    is_assignee: bool = False,
    has_assignee: bool = True,
) -> TransitionCheck:
    """Decide whether this actor may move an issue from `current` to `target`."""
    if current == target:
        return TransitionCheck(False, "The issue is already in that status")
    if target not in allowed_targets(current):
        readable = ", ".join(sorted(s.value for s in allowed_targets(current))) or "nothing"
        return TransitionCheck(False, f"Cannot move from {current.value} to {target.value}; allowed: {readable}")
    if role not in ROLES_THAT_MAY_TRANSITION:
        return TransitionCheck(False, f"{role.value} may not change issue status")
    if target == IssueStatus.CLOSED and role not in ROLES_THAT_MAY_CLOSE:
        return TransitionCheck(False, "Only a manager or admin may close an issue")
    if target == IssueStatus.IN_PROGRESS and not has_assignee and not is_assignee:
        return TransitionCheck(False, "Assign the issue before starting work on it")
    if target == IssueStatus.DONE and role == Role.DEVELOPER and is_assignee:
        # The author of the work does not get to mark their own work reviewed.
        return TransitionCheck(False, "The assignee cannot mark their own issue DONE")
    return TransitionCheck(True)


def validate_transition(current: IssueStatus, target: IssueStatus, **kwargs) -> None:
    """Raise `TransitionError` when the move is not permitted."""
    check = check_transition(current, target, **kwargs)
    if not check.allowed:
        raise TransitionError(check.reason)


def is_terminal(status: IssueStatus) -> bool:
    return status in TERMINAL


def sort_key(issue) -> tuple:
    """Backlog ordering: most urgent first, oldest first within a priority."""
    return (PRIORITY_ORDER.get(issue.priority, 99), issue.created_at)


def issue_key(project_key: str, number: int) -> str:
    return f"{project_key.upper()}-{number}"
