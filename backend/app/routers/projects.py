"""Projects and their membership."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.database import get_db
from app.deps import authorize, get_current_user, get_project, principal_for
from app.models import Activity, Issue, IssueStatus, Project, ProjectMember, Role, User
from app.schemas import MemberAdd, MemberOut, ProjectCreate, ProjectOut, ProjectUpdate
from app.services.permissions import Action, can

router = APIRouter(prefix="/api/projects", tags=["projects"])


def to_out(db: Session, project: Project) -> ProjectOut:
    members = [
        MemberOut(
            id=m.id,
            user_id=m.user_id,
            username=m.user.username if m.user else "",
            role=m.role,
            added_at=m.added_at,
        )
        for m in project.members
    ]
    total = db.scalar(select(func.count()).select_from(Issue).where(Issue.project_id == project.id)) or 0
    open_issues = (
        db.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.project_id == project.id,
                Issue.status.notin_([IssueStatus.DONE, IssueStatus.CLOSED]),
            )
        )
        or 0
    )
    return ProjectOut(
        id=project.id,
        key=project.key,
        name=project.name,
        description=project.description,
        is_archived=project.is_archived,
        created_at=project.created_at,
        open_issues=open_issues,
        total_issues=total,
        members=members,
    )


def log(db: Session, project: Project, user: User, action: str, summary: str, **detail) -> None:
    db.add(
        Activity(
            project_id=project.id,
            actor_id=user.id,
            actor_username=user.username,
            action=action,
            summary=summary[:255],
            detail=detail,
        )
    )


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    include_archived: bool = Query(default=False),
) -> list[ProjectOut]:
    """Admins and managers see everything; everyone else sees their projects."""
    query = select(Project)
    if not include_archived:
        query = query.where(Project.is_archived.is_(False))
    if user.role not in (Role.ADMIN, Role.MANAGER):
        query = query.join(ProjectMember).where(ProjectMember.user_id == user.id)
    return [to_out(db, p) for p in db.scalars(query.order_by(Project.key)).all()]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    authorize(db, user, None, Action.CREATE_PROJECT)
    if db.scalar(select(Project).where(Project.key == payload.key)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project key already in use")

    project = Project(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        created_by_id=user.id,
        issue_counter=0,
    )
    db.add(project)
    db.flush()
    # The creator is a manager of their own project, whatever their global role.
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=Role.MANAGER))
    log(db, project, user, "PROJECT_CREATED", f"Created project {project.key}")
    db.commit()
    db.refresh(project)

    audit.record(
        db, username=user.username, action="CREATE_PROJECT", resource=f"project:{project.key}", request=request
    )
    return to_out(db, project)


@router.get("/{project_key}", response_model=ProjectOut)
def get_one(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    principal = principal_for(db, user, project)
    # Viewing needs membership, or a global role that spans projects.
    if principal.project_role is None and user.role not in (Role.ADMIN, Role.MANAGER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this project")
    if not can(principal, Action.VIEW_PROJECT):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
    return to_out(db, project)


@router.patch("/{project_key}", response_model=ProjectOut)
def update_project(
    payload: ProjectUpdate,
    request: Request,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    authorize(db, user, project, Action.EDIT_PROJECT)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    log(db, project, user, "PROJECT_UPDATED", f"Updated {project.key}", fields=sorted(changes))
    db.commit()
    db.refresh(project)
    audit.record(
        db,
        username=user.username,
        action="UPDATE_PROJECT",
        resource=f"project:{project.key}",
        request=request,
        detail={"fields": sorted(changes)},
    )
    return to_out(db, project)


@router.post("/{project_key}/members", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def add_member(
    payload: MemberAdd,
    request: Request,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    authorize(db, user, project, Action.MANAGE_MEMBERS)
    member_user = db.scalar(select(User).where(User.username == payload.username))
    if member_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == member_user.id)
    )
    if existing is not None:
        existing.role = payload.role
    else:
        db.add(ProjectMember(project_id=project.id, user_id=member_user.id, role=payload.role))
    log(
        db,
        project,
        user,
        "MEMBER_ADDED",
        f"{payload.username} joined as {payload.role.value}",
        username=payload.username,
        role=payload.role.value,
    )
    db.commit()
    db.refresh(project)
    audit.record(
        db,
        username=user.username,
        action="ADD_MEMBER",
        resource=f"project:{project.key}",
        request=request,
        detail={"member": payload.username, "role": payload.role.value},
    )
    return to_out(db, project)


@router.delete("/{project_key}/members/{username}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    username: str,
    request: Request,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    authorize(db, user, project, Action.MANAGE_MEMBERS)
    member = db.scalar(
        select(ProjectMember).join(User).where(ProjectMember.project_id == project.id, User.username == username)
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of this project")

    managers = [m for m in project.members if m.role in (Role.MANAGER, Role.ADMIN)]
    if member.role in (Role.MANAGER, Role.ADMIN) and len(managers) == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A project must keep at least one manager",
        )

    db.delete(member)
    log(db, project, user, "MEMBER_REMOVED", f"{username} left the project", username=username)
    db.commit()
    audit.record(
        db,
        username=user.username,
        action="REMOVE_MEMBER",
        resource=f"project:{project.key}",
        request=request,
        detail={"member": username},
    )
