"""API Keys Routes - Issue/list/revoke API keys for the authenticated user,
backed by the real `api_keys` table (previously not exposed over HTTP at
all).

The raw key is only ever returned once, at creation time — only its bcrypt
hash and a short unrevealing prefix (for display/lookup) are stored,
mirroring how user passwords are handled in api/auth_utils.py.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from database.db import get_db
from database.models import ApiKey, User

router = APIRouter()

_KEY_PREFIX = "arena_"


class ApiKeyCreate(BaseModel):
    """API key creation request."""
    name: str
    permissions: list[str] = []
    rate_limit: int = 100
    expires_in_days: Optional[int] = None


class ApiKeyCreatedResponse(BaseModel):
    """Response for a freshly created key — includes the raw key exactly
    once. It cannot be retrieved again after this response."""
    id: str
    name: str
    api_key: str
    key_prefix: str
    permissions: list[str]
    rate_limit: int
    expires_at: Optional[str]
    created_at: str


class ApiKeyResponse(BaseModel):
    """API key metadata (never includes the raw key or its hash)."""
    id: str
    name: str
    key_prefix: str
    permissions: list
    rate_limit: int
    expires_at: Optional[str]
    last_used_at: Optional[str]
    created_at: str


def _to_response(key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        permissions=key.permissions,
        rate_limit=key.rate_limit,
        expires_at=key.expires_at.isoformat() if key.expires_at else None,
        last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
        created_at=key.created_at.isoformat(),
    )


def _hash_key(raw_key: str) -> str:
    return bcrypt.hashpw(raw_key.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyResponse]:
    """List the current user's API keys (metadata only, never raw keys)."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc())
    )
    return [_to_response(k) for k in result.scalars().all()]


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedResponse:
    """Create a new API key for the current user. The raw key is returned
    only in this response — store it now, it can't be shown again."""
    raw_key = f"{_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    display_prefix = raw_key[: len(_KEY_PREFIX) + 6]

    expires_at = None
    if payload.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

    db_key = ApiKey(
        user_id=current_user.id,
        name=payload.name,
        key_hash=_hash_key(raw_key),
        key_prefix=display_prefix,
        permissions=payload.permissions,
        rate_limit=payload.rate_limit,
        expires_at=expires_at,
    )
    db.add(db_key)
    await db.commit()
    await db.refresh(db_key)

    return ApiKeyCreatedResponse(
        id=db_key.id,
        name=db_key.name,
        api_key=raw_key,
        key_prefix=db_key.key_prefix,
        permissions=db_key.permissions,
        rate_limit=db_key.rate_limit,
        expires_at=db_key.expires_at.isoformat() if db_key.expires_at else None,
        created_at=db_key.created_at.isoformat(),
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke (delete) one of the current user's API keys."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await db.delete(key)
    await db.commit()
