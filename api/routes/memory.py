"""Memory Routes - Memory management endpoints, backed by the real `memories` table.

NOTE: search here is a plain SQL substring match (Memory.content LIKE), not
real vector/semantic similarity search. The schema (embedding VECTOR(1536))
is designed for pgvector cosine similarity in a real Postgres deployment;
that requires generating real embeddings (e.g. via an embeddings API) and
switching database/models.py's embedding column + this query to pgvector's
`<=>` operator, neither of which is wired up yet.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import Memory

router = APIRouter()

# Mirrors core.memory_manager.manager.MemoryManager's forgetting-curve
# constants, applied here directly against the DB-backed `memories` table
# (the in-process MemoryManager operates on its own separate in-memory
# store, not this table — see FIXES.md).
_FORGETTING_THRESHOLD = 0.1
_MAX_ACCESS_AGE_SECONDS = 86400 * 30


class MemoryCreate(BaseModel):
    """Memory creation request."""
    content: str
    memory_type: str = "episodic"
    importance: float = 0.5
    agent_id: Optional[str] = None


class MemoryResponse(BaseModel):
    """Memory response."""
    id: str
    content: str
    memory_type: str
    importance: float
    created_at: str


class MemorySearchResponse(BaseModel):
    """Memory search response."""
    results: list[MemoryResponse]
    total: int


def _to_response(memory: Memory) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        content=memory.content,
        memory_type=memory.memory_type,
        importance=memory.importance,
        created_at=memory.created_at.isoformat(),
    )


@router.get("", response_model=MemorySearchResponse)
async def search_memory(
    query: str,
    agent_id: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> MemorySearchResponse:
    """Search memories by a plain-text substring match (see module docstring
    for why this isn't real vector similarity search yet)."""
    stmt = select(Memory).where(Memory.content.ilike(f"%{query}%"))
    if agent_id:
        stmt = stmt.where(Memory.agent_id == agent_id)
    stmt = stmt.order_by(Memory.importance.desc()).limit(limit)

    result = await db.execute(stmt)
    memories = result.scalars().all()
    return MemorySearchResponse(results=[_to_response(m) for m in memories], total=len(memories))


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def add_memory(memory: MemoryCreate, db: AsyncSession = Depends(get_db)) -> MemoryResponse:
    """Add a new memory."""
    db_memory = Memory(
        agent_id=memory.agent_id,
        memory_type=memory.memory_type,
        content=memory.content,
        importance=memory.importance,
    )
    db.add(db_memory)
    await db.commit()
    await db.refresh(db_memory)
    return _to_response(db_memory)


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: str, db: AsyncSession = Depends(get_db)) -> MemoryResponse:
    """Get memory by ID."""
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return _to_response(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a memory."""
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    await db.delete(memory)
    await db.commit()


@router.post("/consolidate")
async def consolidate_memories(db: AsyncSession = Depends(get_db)) -> dict:
    """Trigger memory consolidation.

    Applies the same forgetting-curve logic as
    core.memory_manager.manager.MemoryManager.consolidate_memories, but
    directly against the DB-backed `memories` table: importance decays
    based on time since last access, and memories that decay below the
    forgetting threshold are deleted. Memories that have never been
    accessed are left untouched (no access history to decay from yet).
    """
    result = await db.execute(select(Memory).where(Memory.last_accessed_at.is_not(None)))
    memories = result.scalars().all()

    now = datetime.now(timezone.utc)
    decayed = 0
    forgotten = 0

    for memory in memories:
        last_accessed = memory.last_accessed_at
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=timezone.utc)
        time_since_access = (now - last_accessed).total_seconds()
        decay = min(1.0, time_since_access / _MAX_ACCESS_AGE_SECONDS)
        memory.importance = max(0.0, memory.importance - (decay * 0.1))
        decayed += 1

        if memory.importance < _FORGETTING_THRESHOLD:
            await db.delete(memory)
            forgotten += 1

    await db.commit()
    return {"status": "completed", "memories_decayed": decayed, "memories_forgotten": forgotten}
