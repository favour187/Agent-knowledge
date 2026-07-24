"""Feedback Routes - Records user/system feedback on agent outputs, backed
by the real `feedback` table (previously not exposed over HTTP at all).
Used by core/self_improvement as a source of training signal.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import Feedback

router = APIRouter()


class FeedbackCreate(BaseModel):
    """Feedback creation request."""
    feedback_type: str
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    context: str = ""
    output: str = ""
    expected: Optional[str] = None
    success: bool = True
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    metadata: dict = {}


class FeedbackResponse(BaseModel):
    """Feedback response."""
    id: str
    agent_id: Optional[str]
    feedback_type: str
    context: Optional[str]
    output: Optional[str]
    expected: Optional[str]
    success: bool
    rating: Optional[int]
    created_at: str


def _to_response(fb: Feedback) -> FeedbackResponse:
    return FeedbackResponse(
        id=fb.id,
        agent_id=fb.agent_id,
        feedback_type=fb.feedback_type,
        context=fb.context,
        output=fb.output,
        expected=fb.expected,
        success=fb.success,
        rating=fb.rating,
        created_at=fb.created_at.isoformat(),
    )


@router.get("", response_model=list[FeedbackResponse])
async def list_feedback(
    agent_id: Optional[str] = None,
    feedback_type: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[FeedbackResponse]:
    """List feedback, optionally filtered by agent or type."""
    stmt = select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
    if agent_id:
        stmt = stmt.where(Feedback.agent_id == agent_id)
    if feedback_type:
        stmt = stmt.where(Feedback.feedback_type == feedback_type)
    result = await db.execute(stmt)
    return [_to_response(f) for f in result.scalars().all()]


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(feedback: FeedbackCreate, db: AsyncSession = Depends(get_db)) -> FeedbackResponse:
    """Record a new piece of feedback."""
    db_feedback = Feedback(
        agent_id=feedback.agent_id,
        user_id=feedback.user_id,
        feedback_type=feedback.feedback_type,
        context=feedback.context,
        output=feedback.output,
        expected=feedback.expected,
        success=feedback.success,
        rating=feedback.rating,
        meta=feedback.metadata,
    )
    db.add(db_feedback)
    await db.commit()
    await db.refresh(db_feedback)
    return _to_response(db_feedback)


@router.get("/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(feedback_id: str, db: AsyncSession = Depends(get_db)) -> FeedbackResponse:
    """Get a feedback record by ID."""
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    fb = result.scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    return _to_response(fb)
