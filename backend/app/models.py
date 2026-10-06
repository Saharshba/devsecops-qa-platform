"""Domain model for the issue tracker.

Two authorisation layers are modelled deliberately:
  * `User.role`          - what a person can do across the whole system
  * `ProjectMember.role` - what they can do inside one project
The resolution of those two is in `app/services/permissions.py` and is where
most of the unit tests point.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; normalise before comparing."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    DEVELOPER = "DEVELOPER"
    VIEWER = "VIEWER"


class IssueStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"
    CLOSED = "CLOSED"


class Priority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IssueType(str, enum.Enum):
    BUG = "BUG"
    FEATURE = "FEATURE"
    TASK = "TASK"
    SECURITY = "SECURITY"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False), default=Role.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list[ProjectMember]] = relationship(back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # e.g. "PAY"
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    # Monotonic per-project counter behind issue keys such as PAY-14.
    issue_counter: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    members: Mapped[list[ProjectMember]] = relationship(back_populates="project", cascade="all, delete-orphan")
    issues: Mapped[list[Issue]] = relationship(back_populates="project")


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False), default=Role.DEVELOPER)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_issue_number"),
        Index("ix_issue_status_priority", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(24), unique=True, index=True)  # "PAY-14"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, native_enum=False), default=IssueStatus.OPEN, index=True
    )
    priority: Mapped[Priority] = mapped_column(Enum(Priority, native_enum=False), default=Priority.MEDIUM, index=True)
    issue_type: Mapped[IssueType] = mapped_column(Enum(IssueType, native_enum=False), default=IssueType.TASK)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="issues")
    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    comments: Mapped[list[Comment]] = relationship(back_populates="issue", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    issue: Mapped[Issue] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()


class Activity(Base):
    """Append-only history of what happened to an issue or project."""

    __tablename__ = "activities"
    __table_args__ = (Index("ix_activity_project_ts", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id"), nullable=True, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(48), index=True)
    summary: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[str] = mapped_column(String(255), default="")
    source_ip: Mapped[str] = mapped_column(String(45), default="")
    outcome: Mapped[str] = mapped_column(String(16), default="SUCCESS")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
