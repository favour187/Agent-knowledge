"""Audit Routes - Read access to the real `audit_logs` table (previously
not exposed over HTTP at all). Logs are written by `log_audit_event()`,
called from sensitive actions elsewhere in the API (e.g. auth.py); this
module only exposes read endpoints, since audit logs should not be editable
or deletable via the API.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import AuditLog

router = APIRouter()


class AuditLogResponse(BaseModel):
    """Audit log entry response."""
    id: str
    user_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[dict]
    created_at: str


def _to_response(log: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=log.id,
        user_id=log.user_id,
        action=log.action,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        details=log.details,
        created_at=log.created_at.isoformat(),
    )


async def log_audit_event(
    db: AsyncSession,
    action: str,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Helper for other routes to record an audit event. Does not commit —
    callers should commit as part of their existing transaction so a failed
    request doesn't leave an orphan audit row."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
    )


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    """List audit log entries, most recent first."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    result = await db.execute(stmt)
    return [_to_response(log) for log in result.scalars().all()]


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(log_id: str, db: AsyncSession = Depends(get_db)) -> AuditLogResponse:
    """Get a single audit log entry by ID."""
    result = await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit log entry not found")
    return _to_response(log)
