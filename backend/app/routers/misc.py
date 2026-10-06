"""Notifications, the dashboard aggregate and the audit trail."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user, require_admin
from app.models import (
    Activity,
    AuditLog,
    Issue,
    IssueStatus,
    Notification,
    Project,
    ProjectMember,
    Role,
    User,
)
from app.schemas import ActivityOut, DashboardOut, NotificationOut, PriorityCount, StatusCount

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[NotificationOut]:
    filters = [Notification.user_id == user.id]
    if unread_only:
        filters.append(Notification.is_read.is_(False))
    rows = db.scalars(select(Notification).where(*filters).order_by(Notification.created_at.desc()).limit(limit)).all()
    return [NotificationOut.model_validate(r) for r in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationOut:
    notification = db.get(Notification, notification_id)
    # Not found rather than forbidden: a user should not learn that someone
    # else's notification exists.
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return NotificationOut.model_validate(notification)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    for notification in db.scalars(
        select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
    ).all():
        notification.is_read = True
    db.commit()


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> DashboardOut:
    """Scoped to what this user can see, not to the whole instance."""
    if user.role in (Role.ADMIN, Role.MANAGER):
        project_ids = [p.id for p in db.scalars(select(Project)).all()]
    else:
        project_ids = [
            m.project_id for m in db.scalars(select(ProjectMember).where(ProjectMember.user_id == user.id)).all()
        ]

    scope = [Issue.project_id.in_(project_ids)] if project_ids else [Issue.id == -1]

    status_rows = db.execute(select(Issue.status, func.count(Issue.id)).where(*scope).group_by(Issue.status)).all()
    priority_rows = db.execute(
        select(Issue.priority, func.count(Issue.id)).where(*scope).group_by(Issue.priority)
    ).all()

    total = sum(count for _, count in status_rows)
    open_issues = sum(
        count for status_value, count in status_rows if status_value not in (IssueStatus.DONE, IssueStatus.CLOSED)
    )

    recent = db.scalars(
        select(Activity)
        .where(Activity.project_id.in_(project_ids) if project_ids else Activity.id == -1)
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(15)
    ).all()

    return DashboardOut(
        generated_at=datetime.now(timezone.utc),
        projects=len(project_ids),
        total_issues=total,
        open_issues=open_issues,
        assigned_to_me=db.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.assignee_id == user.id,
                Issue.status.notin_([IssueStatus.DONE, IssueStatus.CLOSED]),
            )
        )
        or 0,
        unread_notifications=db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        )
        or 0,
        issues_by_status=[StatusCount(status=s, count=c) for s, c in status_rows],
        issues_by_priority=[PriorityCount(priority=p, count=c) for p, c in priority_rows],
        recent_activity=[ActivityOut.model_validate(a) for a in recent],
    )


@router.get("/audit", response_model=list[dict])
def audit_trail(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    filters = [AuditLog.action == action] if action else []
    rows = db.scalars(select(AuditLog).where(*filters).order_by(AuditLog.timestamp.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "username": r.username,
            "action": r.action,
            "resource": r.resource,
            "source_ip": r.source_ip,
            "outcome": r.outcome,
            "detail": r.detail,
        }
        for r in rows
    ]
