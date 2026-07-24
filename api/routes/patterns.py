"""Patterns Routes - Learned request/response patterns used by
core/self_improvement, backed by the real `learned_patterns` table
(previously not exposed over HTTP at all).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import LearnedPattern

router = APIRouter()


class PatternCreate(BaseModel):
    """Learned pattern creation request."""
    agent_id: Optional[str] = None
    pattern_key: str
    context: str = ""
    response: str = ""
    success_rate: float = Field(default=0.5, ge=0, le=1)


class PatternResponse(BaseModel):
    """Learned pattern response."""
    id: str
    agent_id: Optional[str]
    pattern_key: str
    context: Optional[str]
    response: Optional[str]
    success_rate: float
    usage_count: int
    created_at: str


def _to_response(p: LearnedPattern) -> PatternResponse:
    return PatternResponse(
        id=p.id,
        agent_id=p.agent_id,
        pattern_key=p.pattern_key,
        context=p.context,
        response=p.response,
        success_rate=p.success_rate,
        usage_count=p.usage_count,
        created_at=p.created_at.isoformat(),
    )


@router.get("", response_model=list[PatternResponse])
async def list_patterns(
    agent_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[PatternResponse]:
    """List learned patterns, best success rate first."""
    stmt = select(LearnedPattern).order_by(LearnedPattern.success_rate.desc()).limit(limit)
    if agent_id:
        stmt = stmt.where(LearnedPattern.agent_id == agent_id)
    result = await db.execute(stmt)
    return [_to_response(p) for p in result.scalars().all()]


@router.post("", response_model=PatternResponse, status_code=status.HTTP_201_CREATED)
async def upsert_pattern(pattern: PatternCreate, db: AsyncSession = Depends(get_db)) -> PatternResponse:
    """Create (or update, if agent_id + pattern_key already exist) a
    learned pattern."""
    stmt = select(LearnedPattern).where(
        LearnedPattern.agent_id == pattern.agent_id,
        LearnedPattern.pattern_key == pattern.pattern_key,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.context = pattern.context
        existing.response = pattern.response
        existing.success_rate = pattern.success_rate
        existing.usage_count += 1
        db_pattern = existing
    else:
        db_pattern = LearnedPattern(
            agent_id=pattern.agent_id,
            pattern_key=pattern.pattern_key,
            context=pattern.context,
            response=pattern.response,
            success_rate=pattern.success_rate,
        )
        db.add(db_pattern)

    await db.commit()
    await db.refresh(db_pattern)
    return _to_response(db_pattern)


@router.get("/{pattern_id}", response_model=PatternResponse)
async def get_pattern(pattern_id: str, db: AsyncSession = Depends(get_db)) -> PatternResponse:
    """Get a learned pattern by ID."""
    result = await db.execute(select(LearnedPattern).where(LearnedPattern.id == pattern_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    return _to_response(p)


@router.delete("/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pattern(pattern_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a learned pattern."""
    result = await db.execute(select(LearnedPattern).where(LearnedPattern.id == pattern_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    await db.delete(p)
    await db.commit()
