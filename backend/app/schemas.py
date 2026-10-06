"""Request and response models — the API contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import IssueStatus, IssueType, Priority, Role

ORM = ConfigDict(from_attributes=True)


# --- auth ---------------------------------------------------------------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    full_name: str = Field(default="", max_length=128)
    password: str = Field(min_length=12, max_length=128)
    role: Role = Role.DEVELOPER

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        classes = (
            any(c.islower() for c in value),
            any(c.isupper() for c in value),
            any(c.isdigit() for c in value),
            any(not c.isalnum() for c in value),
        )
        if sum(classes) < 3:
            raise ValueError("password must combine at least three of: lowercase, uppercase, digits, symbols")
        return value


class UserOut(BaseModel):
    model_config = ORM
    id: int
    username: str
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


# --- projects -----------------------------------------------------------
class ProjectCreate(BaseModel):
    key: str = Field(min_length=2, max_length=10, pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    name: str = Field(min_length=2, max_length=128)
    description: str = Field(default="", max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    is_archived: bool | None = None


class MemberOut(BaseModel):
    model_config = ORM
    id: int
    user_id: int
    username: str = ""
    role: Role
    added_at: datetime


class MemberAdd(BaseModel):
    username: str
    role: Role = Role.DEVELOPER


class ProjectOut(BaseModel):
    model_config = ORM
    id: int
    key: str
    name: str
    description: str
    is_archived: bool
    created_at: datetime
    open_issues: int = 0
    total_issues: int = 0
    members: list[MemberOut] = Field(default_factory=list)


# --- issues -------------------------------------------------------------
class IssueCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=20000)
    priority: Priority = Priority.MEDIUM
    issue_type: IssueType = IssueType.TASK
    labels: list[str] = Field(default_factory=list, max_length=10)
    assignee: str | None = None

    @field_validator("labels")
    @classmethod
    def _labels(cls, value: list[str]) -> list[str]:
        cleaned = [label.strip().lower() for label in value if label.strip()]
        if any(len(label) > 32 for label in cleaned):
            raise ValueError("labels must be 32 characters or fewer")
        return cleaned


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    priority: Priority | None = None
    issue_type: IssueType | None = None
    labels: list[str] | None = None
    assignee: str | None = None
    status: IssueStatus | None = None


class IssueOut(BaseModel):
    model_config = ORM
    id: int
    key: str
    project_id: int
    number: int
    title: str
    description: str
    status: IssueStatus
    priority: Priority
    issue_type: IssueType
    labels: list[str]
    reporter: str = ""
    assignee: str | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    comment_count: int = 0
    allowed_transitions: list[IssueStatus] = Field(default_factory=list)


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class IssuePage(BaseModel):
    items: list[IssueOut]
    meta: PageMeta


# --- comments, activity, notifications ----------------------------------
class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CommentOut(BaseModel):
    model_config = ORM
    id: int
    issue_id: int
    author: str = ""
    body: str
    created_at: datetime
    edited_at: datetime | None = None


class ActivityOut(BaseModel):
    model_config = ORM
    id: int
    project_id: int
    issue_id: int | None
    actor_username: str
    action: str
    summary: str
    detail: dict[str, Any]
    created_at: datetime


class NotificationOut(BaseModel):
    model_config = ORM
    id: int
    issue_id: int | None
    kind: str
    message: str
    is_read: bool
    created_at: datetime


class StatusCount(BaseModel):
    status: IssueStatus
    count: int


class PriorityCount(BaseModel):
    priority: Priority
    count: int


class DashboardOut(BaseModel):
    generated_at: datetime
    projects: int
    total_issues: int
    open_issues: int
    assigned_to_me: int
    unread_notifications: int
    issues_by_status: list[StatusCount]
    issues_by_priority: list[PriorityCount]
    recent_activity: list[ActivityOut]
