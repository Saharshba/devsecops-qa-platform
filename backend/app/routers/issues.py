"""Issues, comments and the activity feed."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.database import get_db
from app.deps import authorize, get_current_user, get_project, principal_for
from app.models import (
    Activity,
    Comment,
    Issue,
    IssueStatus,
    Notification,
    Priority,
    Project,
    Role,
    User,
)
from app.schemas import (
    ActivityOut,
    CommentCreate,
    CommentOut,
    IssueCreate,
    IssueOut,
    IssuePage,
    IssueUpdate,
    PageMeta,
)
from app.services import notifications as notify
from app.services.permissions import Action, can_edit_own_comment
from app.services.workflow import TransitionError, allowed_targets, issue_key, validate_transition

router = APIRouter(prefix="/api", tags=["issues"])


def to_out(db: Session, issue: Issue, *, role: Role | None = None) -> IssueOut:
    comment_count = db.scalar(select(func.count()).select_from(Comment).where(Comment.issue_id == issue.id)) or 0
    return IssueOut(
        id=issue.id,
        key=issue.key,
        project_id=issue.project_id,
        number=issue.number,
        title=issue.title,
        description=issue.description,
        status=issue.status,
        priority=issue.priority,
        issue_type=issue.issue_type,
        labels=issue.labels or [],
        reporter=issue.reporter.username if issue.reporter else "",
        assignee=issue.assignee.username if issue.assignee else None,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        closed_at=issue.closed_at,
        comment_count=comment_count,
        allowed_transitions=sorted(allowed_targets(issue.status), key=lambda s: s.value),
    )


def log(db: Session, issue: Issue, user: User, action: str, summary: str, **detail) -> None:
    db.add(
        Activity(
            project_id=issue.project_id,
            issue_id=issue.id,
            actor_id=user.id,
            actor_username=user.username,
            action=action,
            summary=summary[:255],
            detail=detail,
        )
    )


def fan_out(db: Session, issue: Issue, specs) -> None:
    for spec in specs:
        db.add(
            Notification(
                user_id=spec.user_id,
                issue_id=issue.id,
                kind=spec.kind,
                message=spec.message,
                is_read=False,
            )
        )


def require_membership(db: Session, user: User, project: Project):
    principal = principal_for(db, user, project)
    if principal.project_role is None and user.role not in (Role.ADMIN, Role.MANAGER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this project")
    return principal


def resolve_assignee(db: Session, project: Project, username: str | None) -> User | None:
    """An assignee must exist and be on the project. Prevents silent mis-assignment."""
    if username in (None, ""):
        return None
    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")
    member_ids = {m.user_id for m in project.members}
    if user.id not in member_ids and user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{username} is not a member of {project.key}",
        )
    return user


@router.post("/projects/{project_key}/issues", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
def create_issue(
    payload: IssueCreate,
    request: Request,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IssueOut:
    require_membership(db, user, project)
    authorize(db, user, project, Action.CREATE_ISSUE)
    if project.is_archived:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project is archived")

    assignee = resolve_assignee(db, project, payload.assignee)

    # The counter lives on the project row, so keys are gapless per project.
    project.issue_counter += 1
    issue = Issue(
        project_id=project.id,
        number=project.issue_counter,
        key=issue_key(project.key, project.issue_counter),
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        issue_type=payload.issue_type,
        labels=payload.labels,
        status=IssueStatus.OPEN,
        reporter_id=user.id,
        assignee_id=assignee.id if assignee else None,
    )
    db.add(issue)
    db.flush()
    log(
        db,
        issue,
        user,
        "ISSUE_CREATED",
        f"{issue.key} created: {issue.title}",
        priority=issue.priority.value,
        type=issue.issue_type.value,
    )
    if assignee:
        fan_out(
            db,
            issue,
            notify.recipients_for_assignment(
                issue_key=issue.key,
                actor_id=user.id,
                new_assignee_id=assignee.id,
                previous_assignee_id=None,
            ),
        )
    db.commit()
    db.refresh(issue)
    audit.record(db, username=user.username, action="CREATE_ISSUE", resource=f"issue:{issue.key}", request=request)
    return to_out(db, issue)


@router.get("/projects/{project_key}/issues", response_model=IssuePage)
def list_issues(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status_filter: IssueStatus | None = Query(default=None, alias="status"),
    priority: Priority | None = None,
    assignee: str | None = None,
    label: str | None = None,
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> IssuePage:
    require_membership(db, user, project)

    filters = [Issue.project_id == project.id]
    if status_filter:
        filters.append(Issue.status == status_filter)
    if priority:
        filters.append(Issue.priority == priority)
    if assignee:
        assignee_user = db.scalar(select(User).where(User.username == assignee))
        filters.append(Issue.assignee_id == (assignee_user.id if assignee_user else -1))
    if search:
        pattern = f"%{search}%"
        filters.append(Issue.title.ilike(pattern) | Issue.description.ilike(pattern))

    total = db.scalar(select(func.count()).select_from(Issue).where(*filters)) or 0
    rows = db.scalars(select(Issue).where(*filters).order_by(Issue.number.desc()).limit(limit).offset(offset)).all()
    if label:
        # Labels are JSON, so filtering happens in Python to stay portable
        # between SQLite and PostgreSQL.
        rows = [row for row in rows if label.lower() in (row.labels or [])]
    return IssuePage(
        items=[to_out(db, row) for row in rows],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


def get_issue_or_404(db: Session, key: str) -> Issue:
    issue = db.scalar(select(Issue).where(Issue.key == key.upper()))
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return issue


@router.get("/issues/{issue_key_path}", response_model=IssueOut)
def get_issue(
    issue_key_path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IssueOut:
    issue = get_issue_or_404(db, issue_key_path)
    require_membership(db, user, issue.project)
    return to_out(db, issue)


@router.patch("/issues/{issue_key_path}", response_model=IssueOut)
def update_issue(
    issue_key_path: str,
    payload: IssueUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IssueOut:
    issue = get_issue_or_404(db, issue_key_path)
    principal = require_membership(db, user, issue.project)
    changes = payload.model_dump(exclude_unset=True)

    if {"title", "description", "priority", "issue_type", "labels"} & changes.keys():
        authorize(db, user, issue.project, Action.EDIT_ISSUE)
    if "assignee" in changes:
        authorize(db, user, issue.project, Action.ASSIGN_ISSUE)
    if "status" in changes:
        authorize(db, user, issue.project, Action.TRANSITION_ISSUE)

    previous_assignee_id = issue.assignee_id

    if "assignee" in changes:
        assignee = resolve_assignee(db, issue.project, changes.pop("assignee"))
        issue.assignee_id = assignee.id if assignee else None
        if issue.assignee_id != previous_assignee_id:
            log(
                db,
                issue,
                user,
                "ISSUE_ASSIGNED",
                f"{issue.key} assigned to {assignee.username if assignee else 'nobody'}",
                assignee=assignee.username if assignee else None,
            )
            fan_out(
                db,
                issue,
                notify.recipients_for_assignment(
                    issue_key=issue.key,
                    actor_id=user.id,
                    new_assignee_id=issue.assignee_id,
                    previous_assignee_id=previous_assignee_id,
                ),
            )

    if "status" in changes:
        target = changes.pop("status")
        try:
            validate_transition(
                issue.status,
                target,
                role=principal.effective_role,
                is_assignee=issue.assignee_id == user.id,
                has_assignee=issue.assignee_id is not None,
            )
        except TransitionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None

        previous = issue.status
        issue.status = target
        issue.closed_at = datetime.now(timezone.utc) if target in (IssueStatus.DONE, IssueStatus.CLOSED) else None
        log(
            db,
            issue,
            user,
            "STATUS_CHANGED",
            f"{issue.key}: {previous.value} → {target.value}",
            **{"from": previous.value, "to": target.value},
        )
        fan_out(
            db,
            issue,
            notify.recipients_for_status_change(
                issue_key=issue.key,
                actor_id=user.id,
                reporter_id=issue.reporter_id,
                assignee_id=issue.assignee_id,
                new_status=target.value,
            ),
        )

    for field, value in changes.items():
        setattr(issue, field, value)
    if changes:
        log(db, issue, user, "ISSUE_UPDATED", f"{issue.key} updated", fields=sorted(changes))

    db.commit()
    db.refresh(issue)
    audit.record(
        db,
        username=user.username,
        action="UPDATE_ISSUE",
        resource=f"issue:{issue.key}",
        request=request,
        detail={"fields": sorted(payload.model_dump(exclude_unset=True))},
    )
    return to_out(db, issue)


@router.delete("/issues/{issue_key_path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(
    issue_key_path: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    issue = get_issue_or_404(db, issue_key_path)
    authorize(db, user, issue.project, Action.DELETE_ISSUE)
    key = issue.key
    db.delete(issue)
    db.commit()
    audit.record(db, username=user.username, action="DELETE_ISSUE", resource=f"issue:{key}", request=request)


# --- comments ------------------------------------------------------------
@router.get("/issues/{issue_key_path}/comments", response_model=list[CommentOut])
def list_comments(
    issue_key_path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CommentOut]:
    issue = get_issue_or_404(db, issue_key_path)
    require_membership(db, user, issue.project)
    rows = db.scalars(select(Comment).where(Comment.issue_id == issue.id).order_by(Comment.created_at)).all()
    return [
        CommentOut(
            id=c.id,
            issue_id=c.issue_id,
            author=c.author.username if c.author else "",
            body=c.body,
            created_at=c.created_at,
            edited_at=c.edited_at,
        )
        for c in rows
    ]


@router.post("/issues/{issue_key_path}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    issue_key_path: str,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CommentOut:
    issue = get_issue_or_404(db, issue_key_path)
    require_membership(db, user, issue.project)
    authorize(db, user, issue.project, Action.COMMENT)

    comment = Comment(issue_id=issue.id, author_id=user.id, body=payload.body)
    db.add(comment)
    db.flush()

    previous = set(db.scalars(select(Comment.author_id).where(Comment.issue_id == issue.id)).all())
    log(db, issue, user, "COMMENT_ADDED", f"{user.username} commented on {issue.key}")
    fan_out(
        db,
        issue,
        notify.recipients_for_comment(
            issue_key=issue.key,
            actor_id=user.id,
            reporter_id=issue.reporter_id,
            assignee_id=issue.assignee_id,
            previous_commenter_ids=previous,
        ),
    )
    db.commit()
    db.refresh(comment)
    return CommentOut(
        id=comment.id,
        issue_id=issue.id,
        author=user.username,
        body=comment.body,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


@router.patch("/comments/{comment_id}", response_model=CommentOut)
def edit_comment(
    comment_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CommentOut:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    principal = principal_for(db, user, comment.issue.project)
    if not can_edit_own_comment(principal, comment.author.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You may only edit your own comments")

    comment.body = payload.body
    comment.edited_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(comment)
    return CommentOut(
        id=comment.id,
        issue_id=comment.issue_id,
        author=comment.author.username,
        body=comment.body,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


# --- activity ------------------------------------------------------------
@router.get("/projects/{project_key}/activity", response_model=list[ActivityOut])
def project_activity(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ActivityOut]:
    require_membership(db, user, project)
    rows = db.scalars(
        select(Activity)
        .where(Activity.project_id == project.id)
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(limit)
    ).all()
    return [ActivityOut.model_validate(r) for r in rows]


@router.get("/issues/{issue_key_path}/activity", response_model=list[ActivityOut])
def issue_activity(
    issue_key_path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ActivityOut]:
    issue = get_issue_or_404(db, issue_key_path)
    require_membership(db, user, issue.project)
    rows = db.scalars(
        select(Activity).where(Activity.issue_id == issue.id).order_by(Activity.created_at, Activity.id).limit(limit)
    ).all()
    return [ActivityOut.model_validate(r) for r in rows]
