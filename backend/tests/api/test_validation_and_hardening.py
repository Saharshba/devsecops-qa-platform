"""Input validation, error handling and transport hardening."""

from __future__ import annotations

import pytest

from app.core.config import settings


@pytest.mark.parametrize(
    "payload",
    [
        {"key": "pay", "name": "lowercase key"},  # keys are upper-case
        {"key": "P", "name": "too short"},
        {"key": "TOOLONGAKEY1", "name": "too long"},
        {"key": "PAY!", "name": "punctuation"},
        {"key": "PAY", "name": "x"},  # name too short
    ],
)
def test_project_payloads_are_validated(client, auth_header, payload):
    assert client.post("/api/projects", json=payload, headers=auth_header("manager")).status_code == 422


def test_validation_errors_name_the_field_without_echoing_the_value(client, auth_header):
    response = client.post("/api/projects", json={"key": "bad-key-value", "name": "x"}, headers=auth_header("manager"))
    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Validation failed"
    assert {error["field"] for error in body["errors"]} == {"key", "name"}
    assert "bad-key-value" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "ab"},  # too short
        {"title": "x" * 201},  # too long
        {"title": "valid", "priority": "URGENT"},  # not in the enum
        {"title": "valid", "issue_type": "EPIC"},
        {"title": "valid", "labels": ["x" * 33]},
        {"title": "valid", "labels": ["a"] * 11},
    ],
)
def test_issue_payloads_are_validated(client, auth_header, project, payload):
    response = client.post("/api/projects/PAY/issues", json=payload, headers=auth_header("dev"))
    assert response.status_code == 422


def test_weak_passwords_are_rejected(client, auth_header):
    for password in ("short", "alllowercaseletters", "PASSWORD1234"):
        response = client.post(
            "/api/auth/users",
            json={"username": "weak", "email": "weak@example.com", "password": password},
            headers=auth_header("admin"),
        )
        assert response.status_code == 422


def test_duplicate_keys_conflict_rather_than_500(client, auth_header, project):
    response = client.post("/api/projects", json={"key": "PAY", "name": "Duplicate"}, headers=auth_header("manager"))
    assert response.status_code == 409


def test_unknown_resources_are_404(client, auth_header, project):
    admin = auth_header("admin")
    assert client.get("/api/projects/NOPE", headers=admin).status_code == 404
    assert client.get("/api/issues/PAY-999", headers=admin).status_code == 404
    assert client.patch("/api/comments/999", json={"body": "x"}, headers=admin).status_code == 404


def test_an_assignee_must_be_a_project_member(client, auth_header, project):
    response = client.post(
        "/api/projects/PAY/issues",
        json={"title": "Wrong assignee", "assignee": "outsider"},
        headers=auth_header("dev"),
    )
    assert response.status_code == 400
    assert "not a member" in response.json()["detail"]


def test_an_unknown_assignee_is_404(client, auth_header, project):
    response = client.post(
        "/api/projects/PAY/issues",
        json={"title": "Ghost", "assignee": "nobody"},
        headers=auth_header("dev"),
    )
    assert response.status_code == 404


def test_invalid_status_transitions_are_rejected_over_http(client, auth_header, issue):
    response = client.patch("/api/issues/PAY-1", json={"status": "DONE"}, headers=auth_header("manager"))
    assert response.status_code == 409
    assert "Cannot move from OPEN to DONE" in response.json()["detail"]


def test_html_in_a_comment_is_stored_verbatim_and_returned_as_json(client, auth_header, issue):
    """No HTML is ever rendered server-side; the payload round-trips as data."""
    payload = '<script>alert("xss")</script>'
    created = client.post("/api/issues/PAY-1/comments", json={"body": payload}, headers=auth_header("dev"))
    assert created.status_code == 201
    assert created.json()["body"] == payload
    assert created.headers["content-type"].startswith("application/json")


def test_sql_metacharacters_in_a_search_are_treated_as_text(client, auth_header, project):
    client.post("/api/projects/PAY/issues", json={"title": "Normal issue"}, headers=auth_header("dev"))
    response = client.get("/api/projects/PAY/issues?search=' OR 1=1 --", headers=auth_header("dev"))
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 0  # parameterised, so nothing matches


def test_pagination_bounds_are_enforced(client, auth_header, project):
    dev = auth_header("dev")
    assert client.get("/api/projects/PAY/issues?limit=0", headers=dev).status_code == 422
    assert client.get("/api/projects/PAY/issues?limit=100000", headers=dev).status_code == 422
    assert client.get("/api/projects/PAY/issues?offset=-1", headers=dev).status_code == 422


def test_security_headers_are_set(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_responses_carry_a_request_id_and_timing(client):
    response = client.get("/health")
    assert response.headers["X-Request-ID"]
    assert float(response.headers["X-Response-Time-ms"]) >= 0


def test_rate_limiting_applies_to_login(client, monkeypatch):
    from app.core import ratelimit

    ratelimit.reset()
    monkeypatch.setattr(settings, "login_rate_limit_requests", 5)
    codes = [client.post("/api/auth/login", json={"username": "dev", "password": "x"}).status_code for _ in range(8)]
    assert 429 in codes
    ratelimit.reset()


def test_health_is_public_and_cheap(client):
    assert client.get("/health").json()["status"] == "ok"


def test_openapi_documents_every_router(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/projects" in paths
    assert "/api/projects/{project_key}/issues" in paths
    assert "/api/dashboard" in paths
