"""Shared fixtures for all three test layers."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-000")
os.environ.setdefault("BCRYPT_ROUNDS", "4")
os.environ.setdefault("RATE_LIMIT_REQUESTS", "100000")
os.environ.setdefault("LOGIN_RATE_LIMIT_REQUESTS", "100000")
os.environ.setdefault("SEED_DEMO_DATA", "false")

from contextlib import asynccontextmanager  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Role, User  # noqa: E402

# One user per global role, plus a second developer for assignment tests.
TEST_USERS = {
    "admin": ("AdminPassw0rd!42", Role.ADMIN),
    "manager": ("ManagerPassw0rd!42", Role.MANAGER),
    "dev": ("DevPassw0rd!42", Role.DEVELOPER),
    "dev2": ("Dev2Passw0rd!42", Role.DEVELOPER),
    "viewer": ("ViewerPassw0rd!42", Role.VIEWER),
    "outsider": ("OutsiderPassw0rd!42", Role.DEVELOPER),
}


@asynccontextmanager
async def _noop_lifespan(app):
    yield


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session_factory):
    from app.core import ratelimit

    ratelimit.reset()
    app = create_app()
    app.router.lifespan_context = _noop_lifespan

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with session_factory() as session:
        for username, (password, role) in TEST_USERS.items():
            session.add(
                User(
                    username=username,
                    email=f"{username}@example.com",
                    full_name=username.title(),
                    hashed_password=hash_password(password),
                    role=role,
                )
            )
        session.commit()

    with TestClient(app) as test_client:
        yield test_client


def token_for(client: TestClient, username: str) -> str:
    password, _ = TEST_USERS[username]
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def auth_header(client):
    def _header(username: str = "admin") -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(client, username)}"}

    return _header


@pytest.fixture
def project(client, auth_header):
    """A project with the whole cast as members, except `outsider`."""
    manager = auth_header("manager")
    created = client.post(
        "/api/projects",
        json={"key": "PAY", "name": "Payments", "description": "Payment platform"},
        headers=manager,
    )
    assert created.status_code == 201, created.text
    for username, role in (("dev", "DEVELOPER"), ("dev2", "DEVELOPER"), ("viewer", "VIEWER")):
        response = client.post("/api/projects/PAY/members", json={"username": username, "role": role}, headers=manager)
        assert response.status_code == 201, response.text
    return created.json()


@pytest.fixture
def issue(client, auth_header, project):
    created = client.post(
        "/api/projects/PAY/issues",
        json={
            "title": "Card tokenisation fails on retry",
            "description": "Steps to reproduce…",
            "priority": "HIGH",
            "issue_type": "BUG",
        },
        headers=auth_header("dev"),
    )
    assert created.status_code == 201, created.text
    return created.json()
