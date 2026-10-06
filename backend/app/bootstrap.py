"""First-run seeding."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import Issue, IssueStatus, IssueType, Priority, Project, ProjectMember, Role, User

logger = logging.getLogger(__name__)


def seed_admin(db: Session) -> User:
    user = db.scalar(select(User).where(User.username == settings.bootstrap_admin_username))
    if user is not None:
        return user
    user = User(
        username=settings.bootstrap_admin_username,
        email=settings.bootstrap_admin_email,
        full_name="Platform administrator",
        hashed_password=hash_password(settings.bootstrap_admin_password),
        role=Role.ADMIN,
    )
    db.add(user)
    db.commit()
    logger.warning("created bootstrap admin %r - change this password now", user.username)
    return user


def seed_demo(db: Session, admin: User) -> None:
    """A single demo project so a fresh instance is not an empty screen.

    Only runs when SEED_DEMO_DATA is set, and never in the test suite.
    """
    if db.scalar(select(Project).where(Project.key == "DEMO")):
        return
    project = Project(
        key="DEMO", name="Demo project", description="Sample data.", created_by_id=admin.id, issue_counter=0
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=admin.id, role=Role.MANAGER))

    samples = [
        ("Harden the login rate limit", Priority.HIGH, IssueType.SECURITY, IssueStatus.OPEN),
        ("Add pagination to the issue list", Priority.MEDIUM, IssueType.FEATURE, IssueStatus.OPEN),
        ("Fix timezone handling in the activity feed", Priority.LOW, IssueType.BUG, IssueStatus.OPEN),
    ]
    for title, priority, issue_type, issue_status in samples:
        project.issue_counter += 1
        db.add(
            Issue(
                project_id=project.id,
                number=project.issue_counter,
                key=f"DEMO-{project.issue_counter}",
                title=title,
                description="",
                priority=priority,
                issue_type=issue_type,
                status=issue_status,
                reporter_id=admin.id,
                labels=[],
            )
        )
    db.commit()
    logger.info("seeded the demo project")


def bootstrap(db: Session) -> None:
    admin = seed_admin(db)
    if settings.seed_demo_data:
        seed_demo(db, admin)
