"""Who gets told when something happens to an issue.

Kept separate from the routers so the fan-out rules - which are easy to get
subtly wrong - can be unit-tested against plain values.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationSpec:
    user_id: int
    kind: str
    message: str


def recipients_for_assignment(
    *, issue_key: str, actor_id: int, new_assignee_id: int | None, previous_assignee_id: int | None
) -> list[NotificationSpec]:
    """Tell the new assignee, and tell the previous one they were unassigned.

    Nobody is ever notified about their own action: self-notifications are the
    fastest way to make people ignore notifications entirely.
    """
    specs: list[NotificationSpec] = []
    if new_assignee_id and new_assignee_id != actor_id:
        specs.append(NotificationSpec(new_assignee_id, "ASSIGNED", f"{issue_key} was assigned to you"))
    if previous_assignee_id and previous_assignee_id not in (actor_id, new_assignee_id):
        specs.append(NotificationSpec(previous_assignee_id, "UNASSIGNED", f"{issue_key} was reassigned"))
    return specs


def recipients_for_status_change(
    *, issue_key: str, actor_id: int, reporter_id: int, assignee_id: int | None, new_status: str
) -> list[NotificationSpec]:
    """The reporter and the assignee both care; the actor does not."""
    interested = {reporter_id, assignee_id} - {None, actor_id}
    return [
        NotificationSpec(user_id, "STATUS_CHANGED", f"{issue_key} moved to {new_status}")
        for user_id in sorted(user_id for user_id in interested if user_id)
    ]


def recipients_for_comment(
    *,
    issue_key: str,
    actor_id: int,
    reporter_id: int,
    assignee_id: int | None,
    previous_commenter_ids: set[int] | None = None,
) -> list[NotificationSpec]:
    """Everyone already involved in the conversation, minus the commenter."""
    interested = {reporter_id, assignee_id} | (previous_commenter_ids or set())
    interested -= {None, actor_id}
    return [
        NotificationSpec(user_id, "COMMENTED", f"New comment on {issue_key}")
        for user_id in sorted(user_id for user_id in interested if user_id)
    ]
