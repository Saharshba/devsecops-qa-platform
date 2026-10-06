"""Authorisation.

Two layers combine: a global role and, optionally, a role inside one project.
The rule is "the stronger of the two wins", because a DEVELOPER who has been
made MANAGER of one project should have manager powers there and nowhere else.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from app.models import Role

# Rank, so "at least MANAGER" is expressible without listing roles everywhere.
RANK = {Role.VIEWER: 0, Role.DEVELOPER: 1, Role.MANAGER: 2, Role.ADMIN: 3}


class Action(str, enum.Enum):
    VIEW_PROJECT = "VIEW_PROJECT"
    CREATE_PROJECT = "CREATE_PROJECT"
    EDIT_PROJECT = "EDIT_PROJECT"
    ARCHIVE_PROJECT = "ARCHIVE_PROJECT"
    MANAGE_MEMBERS = "MANAGE_MEMBERS"
    CREATE_ISSUE = "CREATE_ISSUE"
    EDIT_ISSUE = "EDIT_ISSUE"
    ASSIGN_ISSUE = "ASSIGN_ISSUE"
    TRANSITION_ISSUE = "TRANSITION_ISSUE"
    DELETE_ISSUE = "DELETE_ISSUE"
    COMMENT = "COMMENT"
    MANAGE_USERS = "MANAGE_USERS"


MINIMUM_ROLE: dict[Action, Role] = {
    Action.VIEW_PROJECT: Role.VIEWER,
    Action.CREATE_PROJECT: Role.MANAGER,
    Action.EDIT_PROJECT: Role.MANAGER,
    Action.ARCHIVE_PROJECT: Role.MANAGER,
    Action.MANAGE_MEMBERS: Role.MANAGER,
    Action.CREATE_ISSUE: Role.DEVELOPER,
    Action.EDIT_ISSUE: Role.DEVELOPER,
    Action.ASSIGN_ISSUE: Role.DEVELOPER,
    Action.TRANSITION_ISSUE: Role.DEVELOPER,
    Action.DELETE_ISSUE: Role.ADMIN,
    Action.COMMENT: Role.DEVELOPER,
    Action.MANAGE_USERS: Role.ADMIN,
}

# Actions that are not about one project, so project membership is irrelevant.
GLOBAL_ACTIONS = {Action.CREATE_PROJECT, Action.MANAGE_USERS}


@dataclass(frozen=True)
class Principal:
    """Who is acting, and with what role in the project being acted on."""

    username: str
    global_role: Role
    project_role: Role | None = None
    is_active: bool = True

    @property
    def effective_role(self) -> Role:
        """The stronger of the global role and the project role."""
        if self.project_role is None:
            return self.global_role
        return max(self.global_role, self.project_role, key=lambda role: RANK[role])


def can(principal: Principal, action: Action) -> bool:
    if not principal.is_active:
        return False
    required = MINIMUM_ROLE[action]
    role = principal.global_role if action in GLOBAL_ACTIONS else principal.effective_role
    return RANK[role] >= RANK[required]


def require(principal: Principal, action: Action) -> None:
    """Raise `PermissionError` when the principal may not perform `action`."""
    if not can(principal, action):
        raise PermissionError(f"{principal.username} ({principal.effective_role.value}) may not {action.value}")


def can_edit_own_comment(principal: Principal, author_username: str) -> bool:
    """Authors edit their own comments; admins may edit anyone's."""
    return principal.is_active and (principal.username == author_username or principal.global_role == Role.ADMIN)
