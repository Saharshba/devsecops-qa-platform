"""Unit tests for notification fan-out."""

from __future__ import annotations

from app.services.notifications import (
    recipients_for_assignment,
    recipients_for_comment,
    recipients_for_status_change,
)

ACTOR, ALICE, BOB, CAROL = 1, 2, 3, 4


def user_ids(specs) -> set[int]:
    return {spec.user_id for spec in specs}


def test_assignment_notifies_the_new_assignee():
    specs = recipients_for_assignment(
        issue_key="PAY-1", actor_id=ACTOR, new_assignee_id=ALICE, previous_assignee_id=None
    )
    assert user_ids(specs) == {ALICE}
    assert specs[0].kind == "ASSIGNED"
    assert "PAY-1" in specs[0].message


def test_reassignment_tells_both_people():
    specs = recipients_for_assignment(
        issue_key="PAY-1", actor_id=ACTOR, new_assignee_id=BOB, previous_assignee_id=ALICE
    )
    assert user_ids(specs) == {ALICE, BOB}
    assert {s.kind for s in specs} == {"ASSIGNED", "UNASSIGNED"}


def test_nobody_is_notified_about_their_own_action():
    """Self-notifications are the fastest way to train people to ignore them."""
    specs = recipients_for_assignment(
        issue_key="PAY-1", actor_id=ALICE, new_assignee_id=ALICE, previous_assignee_id=None
    )
    assert specs == []


def test_unassigning_yourself_notifies_nobody():
    specs = recipients_for_assignment(
        issue_key="PAY-1", actor_id=ALICE, new_assignee_id=None, previous_assignee_id=ALICE
    )
    assert specs == []


def test_status_change_notifies_the_reporter_and_assignee():
    specs = recipients_for_status_change(
        issue_key="PAY-1", actor_id=CAROL, reporter_id=ALICE, assignee_id=BOB, new_status="DONE"
    )
    assert user_ids(specs) == {ALICE, BOB}
    assert all("DONE" in spec.message for spec in specs)


def test_status_change_by_the_reporter_does_not_notify_the_reporter():
    specs = recipients_for_status_change(
        issue_key="PAY-1", actor_id=ALICE, reporter_id=ALICE, assignee_id=BOB, new_status="DONE"
    )
    assert user_ids(specs) == {BOB}


def test_an_unassigned_issue_only_notifies_the_reporter():
    specs = recipients_for_status_change(
        issue_key="PAY-1", actor_id=CAROL, reporter_id=ALICE, assignee_id=None, new_status="CLOSED"
    )
    assert user_ids(specs) == {ALICE}


def test_comments_notify_everyone_already_in_the_conversation():
    specs = recipients_for_comment(
        issue_key="PAY-1",
        actor_id=CAROL,
        reporter_id=ALICE,
        assignee_id=BOB,
        previous_commenter_ids={CAROL, 5},
    )
    assert user_ids(specs) == {ALICE, BOB, 5}


def test_no_duplicate_notifications_when_reporter_is_also_assignee():
    specs = recipients_for_comment(issue_key="PAY-1", actor_id=CAROL, reporter_id=ALICE, assignee_id=ALICE)
    assert len(specs) == 1 and specs[0].user_id == ALICE
