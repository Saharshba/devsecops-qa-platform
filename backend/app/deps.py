"""Dependencies: current user, global role gate, project principal."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models import Project, ProjectMember, Role, User
from app.services.permissions import Action, Principal, can

bearer = HTTPBearer(auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_ERROR
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.PyJWTError:
        raise CREDENTIALS_ERROR from None

    user = db.scalar(select(User).where(User.username == payload.get("sub")))
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


class RequireGlobalRole:
    def __init__(self, *roles: Role) -> None:
        self.roles = set(roles) | {Role.ADMIN}

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if user.role not in self.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(sorted(r.value for r in self.roles))}",
            )
        return user


require_admin = RequireGlobalRole(Role.ADMIN)
require_manager = RequireGlobalRole(Role.MANAGER)


def principal_for(db: Session, user: User, project: Project | None) -> Principal:
    """Combine the global role with the caller's role inside this project."""
    project_role = None
    if project is not None:
        membership = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
        )
        project_role = membership.role if membership else None
    return Principal(
        username=user.username,
        global_role=user.role,
        project_role=project_role,
        is_active=user.is_active,
    )


def get_project(
    project_key: str = Path(..., min_length=2, max_length=10),
    db: Session = Depends(get_db),
) -> Project:
    project = db.scalar(select(Project).where(Project.key == project_key.upper()))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def authorize(db: Session, user: User, project: Project | None, action: Action) -> Principal:
    """Return the principal, or raise 403. Used by every project-scoped route."""
    principal = principal_for(db, user, project)
    if not can(principal, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{principal.effective_role.value} may not {action.value.replace('_', ' ').lower()}",
        )
    return principal
