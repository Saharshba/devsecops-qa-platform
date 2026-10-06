"""Audit logging: who changed what, recorded alongside the activity feed."""

from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog

logger = logging.getLogger("audit")


def client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def record(
    db: Session,
    *,
    username: str,
    action: str,
    resource: str = "",
    outcome: str = "SUCCESS",
    request: Request | None = None,
    detail: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        username=username,
        action=action,
        resource=resource,
        outcome=outcome,
        source_ip=client_ip(request),
        detail=detail or {},
    )
    db.add(entry)
    if commit:
        db.commit()
    logger.info("%s %s %s -> %s", username, action, resource, outcome)
    return entry
