"""Tools Routes - Tool management and execution endpoints.

Lists and executes the tools actually registered in app_state.tool_registry
(core/tool_manager/registry.py) — previously this route returned two
hardcoded fake tool descriptions and a fake "success" response with no real
execution at all. Real executions are recorded to the `tool_executions`
table.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.state import app_state
from database.db import get_db
from database.models import ToolExecution

router = APIRouter()


class ToolExecute(BaseModel):
    """Tool execution request."""
    tool_name: str
    arguments: dict = {}
    task_id: Optional[str] = None
    agent_id: Optional[str] = None


class ToolResponse(BaseModel):
    """Tool schema response."""
    name: str
    description: str
    category: str
    tool_schema: dict
    requires_confirmation: bool = False


class ToolExecutionResponse(BaseModel):
    """Tool execution response."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0


class ExecutionLogResponse(BaseModel):
    """Recorded tool execution log entry."""
    id: str
    tool_name: str
    success: bool
    duration_ms: Optional[int]
    created_at: str


def _get_registry():
    registry = app_state.tool_registry
    if registry is None:
        # Fallback for contexts where the app lifespan hasn't run (e.g. tests
        # importing this module directly rather than through the app)
        from core.tool_manager.registry import ToolRegistry
        registry = ToolRegistry()
        app_state.tool_registry = registry
    return registry


@router.get("", response_model=list[ToolResponse])
async def list_tools(category: Optional[str] = None) -> list[ToolResponse]:
    """List all available (actually registered) tools."""
    registry = _get_registry()
    cat_filter = None
    if category:
        from core.tool_manager.registry import ToolCategory
        try:
            cat_filter = ToolCategory(category)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown category: {category}")

    tools = registry.list_tools(category=cat_filter)
    return [
        ToolResponse(
            name=t.name,
            description=t.description,
            category=t.category.value,
            tool_schema=t.schema.to_json_schema() if t.schema else {},
            requires_confirmation=t.requires_confirmation,
        )
        for t in tools
    ]


@router.get("/executions", response_model=list[ExecutionLogResponse])
async def list_executions(
    tool_name: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[ExecutionLogResponse]:
    """List recent tool executions from the database."""
    stmt = select(ToolExecution).order_by(ToolExecution.created_at.desc()).limit(limit)
    if tool_name:
        stmt = stmt.where(ToolExecution.tool_name == tool_name)
    result = await db.execute(stmt)
    return [
        ExecutionLogResponse(
            id=e.id,
            tool_name=e.tool_name,
            success=e.success,
            duration_ms=e.duration_ms,
            created_at=e.created_at.isoformat(),
        )
        for e in result.scalars().all()
    ]


@router.get("/{tool_name}", response_model=ToolResponse)
async def get_tool(tool_name: str) -> ToolResponse:
    """Get tool schema by name."""
    registry = _get_registry()
    tool = registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tool not found: {tool_name}")
    return ToolResponse(
        name=tool.name,
        description=tool.description,
        category=tool.category.value,
        tool_schema=tool.schema.to_json_schema() if tool.schema else {},
        requires_confirmation=tool.requires_confirmation,
    )


@router.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(execution: ToolExecute, db: AsyncSession = Depends(get_db)) -> ToolExecutionResponse:
    """Execute a real registered tool and record the execution."""
    registry = _get_registry()
    tool = registry.get_tool(execution.tool_name)
    if not tool or not tool.function:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tool not found: {execution.tool_name}")

    start = time.time()
    success = True
    error_message: Optional[str] = None
    output: Any = None

    try:
        result = await tool.function(**execution.arguments)
        # BaseTool-adapted tools return a ToolResult(success, output, error, ...)
        if hasattr(result, "success"):
            success = result.success
            output = result.output
            error_message = result.error
        else:
            output = result
    except Exception as e:  # noqa: BLE001 - deliberately broad: recording tool failures, not crashing the request
        success = False
        error_message = str(e)

    duration_ms = int((time.time() - start) * 1000)

    db.add(
        ToolExecution(
            task_id=execution.task_id,
            agent_id=execution.agent_id,
            tool_name=execution.tool_name,
            input=execution.arguments,
            output=output if isinstance(output, dict) else ({"value": output} if output is not None else None),
            error=error_message,
            duration_ms=duration_ms,
            success=success,
        )
    )
    await db.commit()

    return ToolExecutionResponse(
        success=success,
        output=output,
        error=error_message,
        execution_time=duration_ms / 1000,
    )
