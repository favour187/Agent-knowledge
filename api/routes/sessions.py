"""Sessions Routes - Conversation session management, backed by the real
`sessions` / `messages` tables."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import ChatMessage, ChatSession

router = APIRouter()


class SessionCreate(BaseModel):
    """Session creation request."""
    agent_id: str
    title: Optional[str] = None
    context: dict = {}


class MessageCreate(BaseModel):
    """Message creation request."""
    content: str
    role: str = "user"


class MessageResponse(BaseModel):
    """Message response."""
    id: str
    role: str
    content: str
    created_at: str


class SessionResponse(BaseModel):
    """Session response."""
    id: str
    agent_id: str
    title: Optional[str]
    message_count: int
    created_at: str
    updated_at: str


async def _get_session_or_404(session_id: str, db: AsyncSession) -> ChatSession:
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def _to_response(session: ChatSession, db: AsyncSession) -> SessionResponse:
    count_result = await db.execute(select(ChatMessage).where(ChatMessage.session_id == session.id))
    message_count = len(count_result.scalars().all())
    return SessionResponse(
        id=session.id,
        agent_id=session.agent_id,
        title=session.title,
        message_count=message_count,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    agent_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """List all sessions."""
    stmt = select(ChatSession).order_by(ChatSession.created_at.desc()).limit(limit)
    if agent_id:
        stmt = stmt.where(ChatSession.agent_id == agent_id)
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [await _to_response(s, db) for s in sessions]


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(session: SessionCreate, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    """Create a new session."""
    db_session = ChatSession(agent_id=session.agent_id, title=session.title, context=session.context)
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)
    return await _to_response(db_session, db)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    """Get session by ID."""
    session = await _get_session_or_404(session_id, db)
    return await _to_response(session, db)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a session."""
    session = await _get_session_or_404(session_id, db)
    await db.delete(session)
    await db.commit()


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(session_id: str, limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[MessageResponse]:
    """Get messages in a session."""
    await _get_session_or_404(session_id, db)
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).limit(limit)
    )
    return [
        MessageResponse(id=m.id, role=m.role, content=m.content, created_at=m.created_at.isoformat())
        for m in result.scalars().all()
    ]


@router.post("/{session_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(session_id: str, message: MessageCreate, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    """Add a message to a session."""
    await _get_session_or_404(session_id, db)
    db_message = ChatMessage(session_id=session_id, role=message.role, content=message.content)
    db.add(db_message)
    await db.commit()
    await db.refresh(db_message)
    return MessageResponse(
        id=db_message.id, role=db_message.role, content=db_message.content, created_at=db_message.created_at.isoformat()
    )
