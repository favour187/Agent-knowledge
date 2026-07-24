"""Evaluation Routes - Records and lists self-evaluation results, backed by
the real `evaluation_results` table (previously not exposed over HTTP at
all). `POST /run` calls through to the real
core.self_evaluation.evaluator.SelfEvaluator (app_state.self_evaluator) and
persists the result; if no evaluator/AI provider is configured it returns a
clear error rather than fabricating a score.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.state import app_state
from database.db import get_db
from database.models import EvaluationResult

router = APIRouter()


class EvaluationRunRequest(BaseModel):
    """Request to evaluate a piece of output."""
    output: str
    task: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    rubric_name: Optional[str] = None


class EvaluationResponse(BaseModel):
    """Evaluation result response."""
    id: str
    agent_id: Optional[str]
    task_id: Optional[str]
    output: str
    task: Optional[str]
    overall_score: Optional[float]
    dimension_scores: Optional[dict]
    passed: bool
    issues: list
    suggestions: list
    rubric_name: Optional[str]
    created_at: str


def _to_response(e: EvaluationResult) -> EvaluationResponse:
    return EvaluationResponse(
        id=e.id,
        agent_id=e.agent_id,
        task_id=e.task_id,
        output=e.output,
        task=e.task,
        overall_score=e.overall_score,
        dimension_scores=e.dimension_scores,
        passed=e.passed,
        issues=e.issues,
        suggestions=e.suggestions,
        rubric_name=e.rubric_name,
        created_at=e.created_at.isoformat(),
    )


@router.get("", response_model=list[EvaluationResponse])
async def list_evaluations(
    agent_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[EvaluationResponse]:
    """List evaluation results, optionally filtered by agent."""
    stmt = select(EvaluationResult).order_by(EvaluationResult.created_at.desc()).limit(limit)
    if agent_id:
        stmt = stmt.where(EvaluationResult.agent_id == agent_id)
    result = await db.execute(stmt)
    return [_to_response(e) for e in result.scalars().all()]


@router.post("/run", response_model=EvaluationResponse, status_code=status.HTTP_201_CREATED)
async def run_evaluation(request: EvaluationRunRequest, db: AsyncSession = Depends(get_db)) -> EvaluationResponse:
    """Run a real evaluation via core.self_evaluation.evaluator.SelfEvaluator
    and persist the result. Uses the AIRuntime for AI-scored evaluation when
    a provider is configured (OPENAI_API_KEY / ANTHROPIC_API_KEY); otherwise
    SelfEvaluator falls back to its built-in heuristic scoring.
    """
    evaluator = app_state.self_evaluator
    if evaluator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Self-evaluator is not initialized (app not started via lifespan).",
        )

    rubric = None
    if request.rubric_name:
        rubric = evaluator.get_rubric(request.rubric_name)
        if rubric is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown rubric: {request.rubric_name}",
            )

    try:
        eval_result = await evaluator.evaluate(
            output=request.output,
            task=request.task or "",
            rubric=rubric,
        )
    except Exception as exc:  # noqa: BLE001 - surface as a clear 502, don't crash the request
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Evaluation failed: {exc}",
        ) from exc

    db_result = EvaluationResult(
        agent_id=request.agent_id,
        task_id=request.task_id,
        output=request.output,
        task=request.task,
        overall_score=getattr(eval_result, "overall_score", None),
        dimension_scores={
            k: (v.to_dict() if hasattr(v, "to_dict") else v)
            for k, v in getattr(eval_result, "dimension_scores", {}).items()
        } if getattr(eval_result, "dimension_scores", None) else None,
        passed=getattr(eval_result, "passed", True),
        issues=getattr(eval_result, "issues", []) or [],
        suggestions=getattr(eval_result, "suggestions", []) or [],
        rubric_name=request.rubric_name,
    )
    db.add(db_result)
    await db.commit()
    await db.refresh(db_result)
    return _to_response(db_result)


@router.get("/{evaluation_id}", response_model=EvaluationResponse)
async def get_evaluation(evaluation_id: str, db: AsyncSession = Depends(get_db)) -> EvaluationResponse:
    """Get an evaluation result by ID."""
    result = await db.execute(select(EvaluationResult).where(EvaluationResult.id == evaluation_id))
    e = result.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation result not found")
    return _to_response(e)
