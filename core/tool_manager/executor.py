"""
Tool Executor

Executes tools with context, permissions, and resource management.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from core.tool_manager.registry import Tool, ToolRegistry, ToolResult

logger = structlog.get_logger(__name__)


class ExecutionStatus(str, Enum):
    """Status of a tool execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExecutionContext:
    """
    Context for tool execution.

    Provides information about the execution environment,
    permissions, and resource constraints.
    """
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    timeout: float = 30.0  # Default timeout
    memory_limit: Optional[int] = None  # MB
    cpu_limit: Optional[float] = None  # CPU shares
    permissions: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        """Check if context has a permission."""
        return permission in self.permissions

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "timeout": self.timeout,
            "permissions": self.permissions,
            "environment": self.environment,
            "metadata": self.metadata,
        }


@dataclass
class Execution:
    """A tool execution with tracking."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    context: Optional[ExecutionContext] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[ToolResult] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled: bool = False

    @property
    def duration(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.utcnow() - self.started_at).total_seconds()
        return None


class ToolExecutor:
    """
    Executor for running tools with tracking and resource management.

    Features:
    - Execution tracking and history
    - Timeout handling
    - Resource limits
    - Permission checking
    - Concurrency control
    - Execution callbacks
    """

    def __init__(
        self,
        registry: ToolRegistry,
        max_concurrent: int = 10,
    ):
        self.registry = registry
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._executions: dict[str, Execution] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._callbacks: dict[str, list[callable]] = {
            "before": [],
            "after": [],
            "success": [],
            "failure": [],
        }

        logger.info("tool_executor_initialized", max_concurrent=max_concurrent)

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: Optional[ExecutionContext] = None,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """
        Execute a tool with tracking.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            context: Execution context
            timeout: Optional timeout override

        Returns:
            ToolResult
        """
        execution = Execution(
            tool_name=tool_name,
            arguments=arguments,
            context=context,
        )
        self._executions[execution.id] = execution

        # Apply timeout
        exec_timeout = timeout or (context.timeout if context else 30.0)

        # Emit before callback
        for callback in self._callbacks["before"]:
            try:
                callback(execution)
            except Exception as e:
                logger.warning("callback_failed", error=str(e))

        try:
            # Acquire semaphore
            async with self._semaphore:
                execution.status = ExecutionStatus.RUNNING
                execution.started_at = datetime.utcnow()

                logger.debug(
                    "tool_execution_started",
                    execution_id=execution.id,
                    tool=tool_name,
                )

                # Execute with timeout
                try:
                    result = await asyncio.wait_for(
                        self.registry.execute(tool_name, arguments, context),
                        timeout=exec_timeout,
                    )
                except asyncio.TimeoutError:
                    result = ToolResult(
                        success=False,
                        error=f"Execution timed out after {exec_timeout}s",
                    )

                execution.result = result
                execution.completed_at = datetime.utcnow()

                if result.success:
                    execution.status = ExecutionStatus.COMPLETED
                    for callback in self._callbacks["success"]:
                        try:
                            callback(execution, result)
                        except Exception as e:
                            logger.warning("callback_failed", error=str(e))
                else:
                    execution.status = ExecutionStatus.FAILED
                    for callback in self._callbacks["failure"]:
                        try:
                            callback(execution, result)
                        except Exception as e:
                            logger.warning("callback_failed", error=str(e))

                # Emit after callback
                for callback in self._callbacks["after"]:
                    try:
                        callback(execution, result)
                    except Exception as e:
                        logger.warning("callback_failed", error=str(e))

                return result

        except Exception as e:
            logger.error(
                "tool_execution_error",
                execution_id=execution.id,
                error=str(e),
            )
            execution.status = ExecutionStatus.FAILED
            execution.result = ToolResult(success=False, error=str(e))
            execution.completed_at = datetime.utcnow()
            return execution.result

    async def execute_parallel(
        self,
        tasks: list[tuple[str, dict[str, Any]]],
        context: Optional[ExecutionContext] = None,
    ) -> list[ToolResult]:
        """
        Execute multiple tools in parallel.

        Args:
            tasks: List of (tool_name, arguments) tuples
            context: Execution context

        Returns:
            List of ToolResults
        """
        coros = [
            self.execute(tool_name, arguments, context)
            for tool_name, arguments in tasks
        ]
        return await asyncio.gather(*coros, return_exceptions=True)

    async def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        if execution_id in self._running:
            task = self._running[execution_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            execution = self._executions.get(execution_id)
            if execution:
                execution.status = ExecutionStatus.CANCELLED
                execution.cancelled = True
                execution.completed_at = datetime.utcnow()

            logger.info("execution_cancelled", execution_id=execution_id)
            return True

        return False

    def get_execution(self, execution_id: str) -> Optional[Execution]:
        """Get an execution by ID."""
        return self._executions.get(execution_id)

    def get_running_executions(self) -> list[Execution]:
        """Get all running executions."""
        return [
            e for e in self._executions.values()
            if e.status == ExecutionStatus.RUNNING
        ]

    def get_execution_history(
        self,
        limit: int = 100,
        tool_name: Optional[str] = None,
        status: Optional[ExecutionStatus] = None,
    ) -> list[Execution]:
        """Get execution history."""
        executions = list(self._executions.values())

        if tool_name:
            executions = [e for e in executions if e.tool_name == tool_name]

        if status:
            executions = [e for e in executions if e.status == status]

        # Sort by creation time, newest first
        executions.sort(key=lambda e: e.created_at, reverse=True)

        return executions[:limit]

    def add_callback(
        self,
        event: str,
        callback: callable,
    ) -> None:
        """Add an execution callback."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def get_stats(self) -> dict[str, Any]:
        """Get executor statistics."""
        total = len(self._executions)
        completed = sum(
            1 for e in self._executions.values()
            if e.status == ExecutionStatus.COMPLETED
        )
        failed = sum(
            1 for e in self._executions.values()
            if e.status == ExecutionStatus.FAILED
        )
        running = sum(
            1 for e in self._executions.values()
            if e.status == ExecutionStatus.RUNNING
        )

        avg_duration = 0.0
        completed_executions = [
            e for e in self._executions.values()
            if e.status == ExecutionStatus.COMPLETED and e.duration
        ]
        if completed_executions:
            avg_duration = sum(e.duration for e in completed_executions) / len(completed_executions)

        return {
            "total_executions": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "success_rate": completed / total if total > 0 else 0,
            "avg_duration": avg_duration,
            "max_concurrent": self.max_concurrent,
        }
