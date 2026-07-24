"""Tasks Routes - Task management endpoints, backed by the real `tasks` table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import Task

router = APIRouter()


class TaskCreate(BaseModel):
    """Task creation request."""
    title: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    priority: int = Field(default=0, ge=0, le=100)
    agent_id: Optional[str] = None


class TaskUpdate(BaseModel):
    """Task update request."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None


class TaskResponse(BaseModel):
    """Task response."""
    id: str
    title: str
    description: str
    status: str
    priority: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


def _to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


async def _get_task_or_404(task_id: str, db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks(status: Optional[str] = None, db: AsyncSession = Depends(get_db)) -> list[TaskResponse]:
    """List all tasks, optionally filtered by status."""
    query = select(Task).order_by(Task.created_at.desc())
    if status:
        query = query.where(Task.status == status)
    result = await db.execute(query)
    return [_to_response(t) for t in result.scalars().all()]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)) -> TaskResponse:
    """Create a new task."""
    db_task = Task(
        agent_id=task.agent_id,
        title=task.title,
        description=task.description,
        status="pending",
        priority=task.priority,
    )
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    return _to_response(db_task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)) -> TaskResponse:
    """Get task by ID."""
    task = await _get_task_or_404(task_id, db)
    return _to_response(task)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, update: TaskUpdate, db: AsyncSession = Depends(get_db)) -> TaskResponse:
    """Update a task."""
    task = await _get_task_or_404(task_id, db)

    if update.title is not None:
        task.title = update.title
    if update.description is not None:
        task.description = update.description
    if update.priority is not None:
        task.priority = update.priority
    if update.status is not None:
        old_status = task.status
        task.status = update.status
        if update.status == "running" and old_status != "running":
            task.started_at = datetime.now(timezone.utc)
        if update.status in ("completed", "failed") and old_status not in ("completed", "failed"):
            task.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)
    return _to_response(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a task."""
    task = await _get_task_or_404(task_id, db)
    await db.delete(task)
    await db.commit()
