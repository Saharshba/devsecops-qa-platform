"""Integration tests: the API together with the database.

These check that the pieces agree — a status change writes activity, fans out
notifications, stamps `closed_at` and leaves the issue readable afterwards.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import Comment, Issue, IssueStatus, Notification, Project, User


def transition(client, headers, key, target):
    return client.patch(f"/api/issues/{key}", json={"status": target}, headers=headers)


def test_full_issue_lifecycle(client, auth_header, project, db):
    dev, dev2, manager = auth_header("dev"), auth_header("dev2"), auth_header("manager")

    created = client.post(
        "/api/projects/PAY/issues",
        json={
            "title": "Refunds double-charge on retry",
            "priority": "CRITICAL",
            "issue_type": "BUG",
            "labels": ["Payments", "regression"],
        },
        headers=dev,
    )
    assert created.status_code == 201
    issue = created.json()
    assert issue["key"] == "PAY-1"
    assert issue["status"] == "OPEN"
    assert issue["labels"] == ["payments", "regression"]  # normalised on the way in

    assigned = client.patch("/api/issues/PAY-1", json={"assignee": "dev2"}, headers=dev)
    assert assigned.status_code == 200 and assigned.json()["assignee"] == "dev2"

    assert transition(client, dev2, "PAY-1", "IN_PROGRESS").status_code == 200
    assert transition(client, dev2, "PAY-1", "IN_REVIEW").status_code == 200

    # The assignee may not sign off their own work; another developer may.
    assert transition(client, dev2, "PAY-1", "DONE").status_code == 409
    done = transition(client, dev, "PAY-1", "DONE")
    assert done.status_code == 200
    assert done.json()["closed_at"] is not None

    closed = transition(client, manager, "PAY-1", "CLOSED")
    assert closed.status_code == 200

    stored = db.scalar(select(Issue).where(Issue.key == "PAY-1"))
    assert stored.status == IssueStatus.CLOSED
    assert stored.closed_at is not None


def test_activity_feed_records_each_step(client, auth_header, project):
    dev, dev2 = auth_header("dev"), auth_header("dev2")
    client.post("/api/projects/PAY/issues", json={"title": "Timeout on settlement"}, headers=dev)
    client.patch("/api/issues/PAY-1", json={"assignee": "dev2"}, headers=dev)
    transition(client, dev2, "PAY-1", "IN_PROGRESS")
    client.post("/api/issues/PAY-1/comments", json={"body": "Reproduced locally."}, headers=dev2)

    feed = client.get("/api/issues/PAY-1/activity", headers=dev).json()
    actions = [entry["action"] for entry in feed]
    assert actions == ["ISSUE_CREATED", "ISSUE_ASSIGNED", "STATUS_CHANGED", "COMMENT_ADDED"]
    status_entry = next(e for e in feed if e["action"] == "STATUS_CHANGED")
    assert status_entry["detail"]["from"] == "OPEN" and status_entry["detail"]["to"] == "IN_PROGRESS"


def test_project_activity_includes_membership_changes(client, auth_header, project):
    feed = client.get("/api/projects/PAY/activity", headers=auth_header("manager")).json()
    actions = {entry["action"] for entry in feed}
    assert {"PROJECT_CREATED", "MEMBER_ADDED"} <= actions


def test_notifications_reach_the_right_people(client, auth_header, project, db):
    dev, dev2 = auth_header("dev"), auth_header("dev2")
    client.post("/api/projects/PAY/issues", json={"title": "Webhook retries"}, headers=dev)
    client.patch("/api/issues/PAY-1", json={"assignee": "dev2"}, headers=dev)

    dev2_user = db.scalar(select(User).where(User.username == "dev2"))
    dev_user = db.scalar(select(User).where(User.username == "dev"))

    assigned = db.scalars(select(Notification).where(Notification.user_id == dev2_user.id)).all()
    assert [n.kind for n in assigned] == ["ASSIGNED"]
    # The reporter took the action, so they are not told about their own work.
    assert db.scalars(select(Notification).where(Notification.user_id == dev_user.id)).all() == []

    transition(client, dev2, "PAY-1", "IN_PROGRESS")
    reporter_notifications = db.scalars(select(Notification).where(Notification.user_id == dev_user.id)).all()
    assert [n.kind for n in reporter_notifications] == ["STATUS_CHANGED"]


def test_notifications_can_be_read_and_marked(client, auth_header, project):
    dev, dev2 = auth_header("dev"), auth_header("dev2")
    client.post("/api/projects/PAY/issues", json={"title": "Idempotency keys"}, headers=dev)
    client.patch("/api/issues/PAY-1", json={"assignee": "dev2"}, headers=dev)

    unread = client.get("/api/notifications?unread_only=true", headers=dev2).json()
    assert len(unread) == 1

    marked = client.post(f"/api/notifications/{unread[0]['id']}/read", headers=dev2)
    assert marked.status_code == 200 and marked.json()["is_read"] is True
    assert client.get("/api/notifications?unread_only=true", headers=dev2).json() == []


def test_issue_keys_are_sequential_per_project(client, auth_header, project, db):
    manager, dev = auth_header("manager"), auth_header("dev")
    for title in ("First", "Second", "Third"):
        client.post("/api/projects/PAY/issues", json={"title": title}, headers=dev)

    client.post("/api/projects", json={"key": "OPS", "name": "Operations"}, headers=manager)
    other = client.post("/api/projects/OPS/issues", json={"title": "Rotate keys"}, headers=manager)

    keys = [i["key"] for i in client.get("/api/projects/PAY/issues", headers=dev).json()["items"]]
    assert keys == ["PAY-3", "PAY-2", "PAY-1"]
    # A second project starts its own numbering.
    assert other.json()["key"] == "OPS-1"
    assert db.scalar(select(Project).where(Project.key == "PAY")).issue_counter == 3


def test_comments_are_ordered_and_editable_by_their_author(client, auth_header, issue, db):
    dev, dev2, admin = auth_header("dev"), auth_header("dev2"), auth_header("admin")
    first = client.post("/api/issues/PAY-1/comments", json={"body": "Looking at it."}, headers=dev)
    client.post("/api/issues/PAY-1/comments", json={"body": "Found the cause."}, headers=dev2)
    assert first.status_code == 201

    comments = client.get("/api/issues/PAY-1/comments", headers=dev).json()
    assert [c["author"] for c in comments] == ["dev", "dev2"]

    edited = client.patch(f"/api/comments/{first.json()['id']}", json={"body": "Updated."}, headers=dev)
    assert edited.status_code == 200 and edited.json()["edited_at"] is not None

    # Another developer may not rewrite someone else's comment; an admin may.
    assert client.patch(f"/api/comments/{first.json()['id']}", json={"body": "Nope."}, headers=dev2).status_code == 403
    assert (
        client.patch(f"/api/comments/{first.json()['id']}", json={"body": "Moderated."}, headers=admin).status_code
        == 200
    )

    assert db.scalar(select(Comment).where(Comment.id == first.json()["id"])).body == "Moderated."


def test_deleting_an_issue_removes_its_comments(client, auth_header, issue, db):
    client.post("/api/issues/PAY-1/comments", json={"body": "A note."}, headers=auth_header("dev"))
    assert client.delete("/api/issues/PAY-1", headers=auth_header("admin")).status_code == 204
    assert db.scalars(select(Comment)).all() == []


def test_issue_filters(client, auth_header, project):
    dev = auth_header("dev")
    client.post(
        "/api/projects/PAY/issues",
        json={"title": "Critical bug", "priority": "CRITICAL", "issue_type": "BUG", "labels": ["urgent"]},
        headers=dev,
    )
    client.post(
        "/api/projects/PAY/issues", json={"title": "Small task", "priority": "LOW", "assignee": "dev2"}, headers=dev
    )

    assert client.get("/api/projects/PAY/issues?priority=CRITICAL", headers=dev).json()["meta"]["total"] == 1
    assert client.get("/api/projects/PAY/issues?assignee=dev2", headers=dev).json()["meta"]["total"] == 1
    assert client.get("/api/projects/PAY/issues?search=critical", headers=dev).json()["meta"]["total"] == 1
    assert client.get("/api/projects/PAY/issues?status=OPEN", headers=dev).json()["meta"]["total"] == 2
    labelled = client.get("/api/projects/PAY/issues?label=urgent", headers=dev).json()["items"]
    assert [i["title"] for i in labelled] == ["Critical bug"]


def test_dashboard_reflects_the_users_own_scope(client, auth_header, project):
    dev, outsider = auth_header("dev"), auth_header("outsider")
    client.post("/api/projects/PAY/issues", json={"title": "Visible to members", "assignee": "dev"}, headers=dev)

    member_view = client.get("/api/dashboard", headers=dev).json()
    assert member_view["projects"] == 1
    assert member_view["total_issues"] == 1
    assert member_view["assigned_to_me"] == 1
    assert member_view["issues_by_status"][0]["status"] == "OPEN"

    # Someone with no membership sees an empty dashboard, not everyone's data.
    outsider_view = client.get("/api/dashboard", headers=outsider).json()
    assert outsider_view["projects"] == 0
    assert outsider_view["total_issues"] == 0
    assert outsider_view["recent_activity"] == []


def test_archived_projects_reject_new_issues(client, auth_header, project):
    manager, dev = auth_header("manager"), auth_header("dev")
    client.patch("/api/projects/PAY", json={"is_archived": True}, headers=manager)
    blocked = client.post("/api/projects/PAY/issues", json={"title": "Too late"}, headers=dev)
    assert blocked.status_code == 400
    assert "archived" in blocked.json()["detail"].lower()


def test_a_project_always_keeps_a_manager(client, auth_header, project):
    manager = auth_header("manager")
    removed = client.delete("/api/projects/PAY/members/manager", headers=manager)
    assert removed.status_code == 400
    assert "at least one manager" in removed.json()["detail"]

    client.post("/api/projects/PAY/members", json={"username": "dev", "role": "MANAGER"}, headers=manager)
    assert client.delete("/api/projects/PAY/members/manager", headers=manager).status_code == 204
