"""API-level authentication and authorisation tests.

These are the ones a security review cares about: can a signed-in user reach
something they should not, by guessing a key or calling an endpoint directly?
"""

from __future__ import annotations

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token
from tests.conftest import TEST_USERS

PROTECTED = [
    ("GET", "/api/projects"),
    ("GET", "/api/dashboard"),
    ("GET", "/api/notifications"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/projects"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_protected_endpoint_requires_a_token(client, method, path):
    assert client.request(method, path).status_code == 401


def test_login_and_profile(client):
    body = client.post("/api/auth/login", json={"username": "dev", "password": TEST_USERS["dev"][0]}).json()
    assert body["user"]["role"] == "DEVELOPER"
    assert "hashed_password" not in body["user"]

    profile = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert profile.json()["username"] == "dev"


def test_bad_credentials_are_indistinguishable(client):
    wrong = client.post("/api/auth/login", json={"username": "dev", "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "wrong-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_expired_and_forged_tokens_are_rejected(client, monkeypatch):
    forged = jwt.encode({"sub": "admin", "role": "ADMIN", "type": "access"}, "wrong-key", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401

    monkeypatch.setattr(settings, "access_token_ttl_minutes", -1)
    expired = create_access_token("admin", "ADMIN")
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401 and "expired" in response.json()["detail"].lower()


def test_a_deactivated_user_loses_access_immediately(client, auth_header):
    dev_header = auth_header("dev")
    assert client.get("/api/auth/me", headers=dev_header).status_code == 200

    client.patch("/api/auth/users/dev/deactivate", headers=auth_header("admin"))
    assert client.get("/api/auth/me", headers=dev_header).status_code == 401


def test_an_admin_cannot_deactivate_themselves(client, auth_header):
    response = client.patch("/api/auth/users/admin/deactivate", headers=auth_header("admin"))
    assert response.status_code == 400


# --- project-scoped authorisation ---------------------------------------
def test_only_managers_and_admins_create_projects(client, auth_header):
    payload = {"key": "NEW", "name": "New project"}
    assert client.post("/api/projects", json=payload, headers=auth_header("dev")).status_code == 403
    assert client.post("/api/projects", json=payload, headers=auth_header("viewer")).status_code == 403
    assert client.post("/api/projects", json=payload, headers=auth_header("manager")).status_code == 201


def test_non_members_cannot_read_a_project_or_its_issues(client, auth_header, issue):
    outsider = auth_header("outsider")
    assert client.get("/api/projects/PAY", headers=outsider).status_code == 403
    assert client.get("/api/projects/PAY/issues", headers=outsider).status_code == 403
    assert client.get("/api/issues/PAY-1", headers=outsider).status_code == 403
    assert client.get("/api/issues/PAY-1/comments", headers=outsider).status_code == 403


def test_guessing_an_issue_key_does_not_leak_data(client, auth_header, issue):
    """The classic IDOR check: a valid key, a user with no business seeing it."""
    response = client.get("/api/issues/PAY-1", headers=auth_header("outsider"))
    assert response.status_code == 403
    assert "Card tokenisation" not in response.text


def test_viewers_can_read_but_not_write(client, auth_header, issue):
    viewer = auth_header("viewer")
    assert client.get("/api/issues/PAY-1", headers=viewer).status_code == 200
    assert client.post("/api/projects/PAY/issues", json={"title": "Nope"}, headers=viewer).status_code == 403
    assert client.post("/api/issues/PAY-1/comments", json={"body": "Nope"}, headers=viewer).status_code == 403
    assert client.patch("/api/issues/PAY-1", json={"status": "IN_PROGRESS"}, headers=viewer).status_code == 403


def test_developers_cannot_manage_members_or_delete_issues(client, auth_header, issue):
    dev = auth_header("dev")
    assert client.post("/api/projects/PAY/members", json={"username": "outsider"}, headers=dev).status_code == 403
    assert client.delete("/api/issues/PAY-1", headers=dev).status_code == 403


def test_a_project_role_grants_powers_only_inside_that_project(client, auth_header):
    """dev is a manager of OPS, which must not let them manage PAY."""
    manager, dev = auth_header("manager"), auth_header("dev")
    client.post("/api/projects", json={"key": "PAY", "name": "Payments"}, headers=manager)
    client.post("/api/projects", json={"key": "OPS", "name": "Operations"}, headers=manager)
    client.post("/api/projects/OPS/members", json={"username": "dev", "role": "MANAGER"}, headers=manager)
    client.post("/api/projects/PAY/members", json={"username": "dev", "role": "DEVELOPER"}, headers=manager)

    assert client.post("/api/projects/OPS/members", json={"username": "dev2"}, headers=dev).status_code == 201
    assert client.post("/api/projects/PAY/members", json={"username": "dev2"}, headers=dev).status_code == 403


def test_only_admins_manage_users_and_read_the_audit_trail(client, auth_header):
    payload = {"username": "newbie", "email": "newbie@example.com", "password": "Str0ng!Password1"}
    assert client.post("/api/auth/users", json=payload, headers=auth_header("manager")).status_code == 403
    assert client.get("/api/audit", headers=auth_header("manager")).status_code == 403
    assert client.post("/api/auth/users", json=payload, headers=auth_header("admin")).status_code == 201
    assert client.get("/api/audit", headers=auth_header("admin")).status_code == 200


def test_notifications_are_private_to_their_owner(client, auth_header, project):
    dev, dev2 = auth_header("dev"), auth_header("dev2")
    client.post("/api/projects/PAY/issues", json={"title": "Alert routing", "assignee": "dev2"}, headers=dev)
    notification_id = client.get("/api/notifications", headers=dev2).json()[0]["id"]

    # Another user gets 404, not 403: they should not learn it exists.
    assert client.post(f"/api/notifications/{notification_id}/read", headers=dev).status_code == 404


def test_login_failures_are_audited(client, auth_header):
    client.post("/api/auth/login", json={"username": "dev", "password": "wrong-password"})
    entries = client.get("/api/audit?action=LOGIN", headers=auth_header("admin")).json()
    assert any(entry["outcome"] == "FAILURE" for entry in entries)
