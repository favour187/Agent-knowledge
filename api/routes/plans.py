"""Plans Routes - Plan and plan-step management, backed by the real `plans`
and `plan_steps` tables (previously not exposed over HTTP at all).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import Plan, PlanStep

router = APIRouter()


class PlanStepCreate(BaseModel):
    """Plan step creation request."""
    title: str
    description: str = ""
    priority: int = 0
    dependencies: list[str] = []


class PlanStepUpdate(BaseModel):
    """Plan step update request."""
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None


class PlanStepResponse(BaseModel):
    """Plan step response."""
    id: str
    plan_id: str
    title: str
    description: str
    status: str
    priority: int
    dependencies: list
    result: Optional[dict]
    error: Optional[str]
    created_at: str


class PlanCreate(BaseModel):
    """Plan creation request."""
    goal: str
    agent_id: Optional[str] = None
    steps: list[PlanStepCreate] = []


class PlanUpdate(BaseModel):
    """Plan update request."""
    status: Optional[str] = None
    progress: Optional[float] = None
    result: Optional[dict] = None


class PlanResponse(BaseModel):
    """Plan response."""
    id: str
    agent_id: Optional[str]
    goal: str
    status: str
    progress: float
    result: Optional[dict]
    created_at: str
    steps: list[PlanStepResponse] = []


def _step_to_response(step: PlanStep) -> PlanStepResponse:
    return PlanStepResponse(
        id=step.id,
        plan_id=step.plan_id,
        title=step.title,
        description=step.description,
        status=step.status,
        priority=step.priority,
        dependencies=step.dependencies,
        result=step.result,
        error=step.error,
        created_at=step.created_at.isoformat(),
    )


def _plan_to_response(plan: Plan) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        agent_id=plan.agent_id,
        goal=plan.goal,
        status=plan.status,
        progress=plan.progress,
        result=plan.result,
        created_at=plan.created_at.isoformat(),
        steps=[_step_to_response(s) for s in plan.steps] if plan.steps is not None else [],
    )


async def _get_plan_or_404(plan_id: str, db: AsyncSession) -> Plan:
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


@router.get("", response_model=list[PlanResponse])
async def list_plans(
    agent_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[PlanResponse]:
    """List plans, optionally filtered by agent or status."""
    stmt = select(Plan).order_by(Plan.created_at.desc())
    if agent_id:
        stmt = stmt.where(Plan.agent_id == agent_id)
    if status_filter:
        stmt = stmt.where(Plan.status == status_filter)
    result = await db.execute(stmt)
    return [_plan_to_response(p) for p in result.scalars().all()]


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(plan: PlanCreate, db: AsyncSession = Depends(get_db)) -> PlanResponse:
    """Create a new plan, optionally with initial steps."""
    db_plan = Plan(agent_id=plan.agent_id, goal=plan.goal, status="planning")
    for i, step in enumerate(plan.steps):
        db_plan.steps.append(
            PlanStep(
                title=step.title,
                description=step.description,
                priority=step.priority or i,
                dependencies=step.dependencies,
            )
        )
    db.add(db_plan)
    await db.commit()
    await db.refresh(db_plan, attribute_names=["steps"])
    return _plan_to_response(db_plan)


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db)) -> PlanResponse:
    """Get a plan by ID, including its steps."""
    plan = await _get_plan_or_404(plan_id, db)
    return _plan_to_response(plan)


@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(plan_id: str, update: PlanUpdate, db: AsyncSession = Depends(get_db)) -> PlanResponse:
    """Update a plan's status/progress/result."""
    plan = await _get_plan_or_404(plan_id, db)
    if update.status is not None:
        plan.status = update.status
    if update.progress is not None:
        plan.progress = update.progress
    if update.result is not None:
        plan.result = update.result
    await db.commit()
    await db.refresh(plan, attribute_names=["steps"])
    return _plan_to_response(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(plan_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a plan and its steps."""
    plan = await _get_plan_or_404(plan_id, db)
    await db.delete(plan)
    await db.commit()


@router.post("/{plan_id}/steps", response_model=PlanStepResponse, status_code=status.HTTP_201_CREATED)
async def add_plan_step(plan_id: str, step: PlanStepCreate, db: AsyncSession = Depends(get_db)) -> PlanStepResponse:
    """Add a step to an existing plan."""
    await _get_plan_or_404(plan_id, db)
    db_step = PlanStep(
        plan_id=plan_id,
        title=step.title,
        description=step.description,
        priority=step.priority,
        dependencies=step.dependencies,
    )
    db.add(db_step)
    await db.commit()
    await db.refresh(db_step)
    return _step_to_response(db_step)


@router.put("/steps/{step_id}", response_model=PlanStepResponse)
async def update_plan_step(
    step_id: str,
    update: PlanStepUpdate,
    db: AsyncSession = Depends(get_db),
) -> PlanStepResponse:
    """Update a plan step's status/result/error."""
    db_result = await db.execute(select(PlanStep).where(PlanStep.id == step_id))
    db_step = db_result.scalar_one_or_none()
    if not db_step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan step not found")

    db_step.status = update.status
    if update.result is not None:
        db_step.result = update.result
    if update.error is not None:
        db_step.error = update.error
    await db.commit()
    await db.refresh(db_step)
    return _step_to_response(db_step)
