"""Unit tests for the two-layer authorisation model."""

from __future__ import annotations

import pytest

from app.models import Role
from app.services.permissions import (
    Action,
    Principal,
    can,
    can_edit_own_comment,
    require,
)


def principal(global_role: Role, project_role: Role | None = None, active: bool = True) -> Principal:
    return Principal(username="u", global_role=global_role, project_role=project_role, is_active=active)


def test_effective_role_is_the_stronger_of_the_two():
    assert principal(Role.DEVELOPER, Role.MANAGER).effective_role == Role.MANAGER
    assert principal(Role.MANAGER, Role.VIEWER).effective_role == Role.MANAGER
    assert principal(Role.VIEWER).effective_role == Role.VIEWER


def test_a_project_role_never_weakens_a_global_role():
    """A global manager stays a manager even in a project where they are a viewer."""
    assert can(principal(Role.MANAGER, Role.VIEWER), Action.EDIT_PROJECT)


def test_a_project_role_can_strengthen_a_global_role():
    assert not can(principal(Role.DEVELOPER), Action.MANAGE_MEMBERS)
    assert can(principal(Role.DEVELOPER, Role.MANAGER), Action.MANAGE_MEMBERS)


@pytest.mark.parametrize(
    "role,action,expected",
    [
        (Role.VIEWER, Action.VIEW_PROJECT, True),
        (Role.VIEWER, Action.CREATE_ISSUE, False),
        (Role.VIEWER, Action.COMMENT, False),
        (Role.DEVELOPER, Action.CREATE_ISSUE, True),
        (Role.DEVELOPER, Action.TRANSITION_ISSUE, True),
        (Role.DEVELOPER, Action.MANAGE_MEMBERS, False),
        (Role.DEVELOPER, Action.DELETE_ISSUE, False),
        (Role.MANAGER, Action.MANAGE_MEMBERS, True),
        (Role.MANAGER, Action.DELETE_ISSUE, False),
        (Role.MANAGER, Action.MANAGE_USERS, False),
        (Role.ADMIN, Action.DELETE_ISSUE, True),
        (Role.ADMIN, Action.MANAGE_USERS, True),
    ],
)
def test_permission_matrix(role, action, expected):
    assert can(principal(role), action) is expected


def test_global_actions_ignore_the_project_role():
    """Being made manager of one project does not grant global powers."""
    assert not can(principal(Role.DEVELOPER, Role.ADMIN), Action.MANAGE_USERS)
    assert not can(principal(Role.DEVELOPER, Role.MANAGER), Action.CREATE_PROJECT)


def test_inactive_users_can_do_nothing():
    disabled = principal(Role.ADMIN, active=False)
    assert not any(can(disabled, action) for action in Action)


def test_require_raises_with_a_useful_message():
    with pytest.raises(PermissionError, match="may not DELETE_ISSUE"):
        require(principal(Role.DEVELOPER), Action.DELETE_ISSUE)


def test_comment_editing_is_limited_to_the_author_or_an_admin():
    author = Principal(username="alice", global_role=Role.DEVELOPER)
    other = Principal(username="bob", global_role=Role.MANAGER)
    admin = Principal(username="root", global_role=Role.ADMIN)

    assert can_edit_own_comment(author, "alice")
    assert not can_edit_own_comment(other, "alice")
    assert can_edit_own_comment(admin, "alice")
