"""
Collaboration Manager

Manages collaborative task execution between agents.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class TaskStatus(str, Enum):
    """Status of a collaborative task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Task priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Task:
    """A collaborative task."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
            "dependencies": self.dependencies,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }


@dataclass
class TaskResult:
    """Result of a collaborative task."""
    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    agent_id: Optional[str] = None
    duration: Optional[float] = None


class CollaborationManager:
    """
    Manages collaborative task execution.

    Features:
    - Task creation and assignment
    - Dependency management
    - Parallel execution
    - Result collection
    - Progress tracking
    """

    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, TaskResult] = {}
        self._callbacks: list[callable] = []

        logger.info("collaboration_manager_initialized")

    def create_task(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: Optional[list[str]] = None,
    ) -> Task:
        """Create a new collaborative task."""
        task = Task(
            description=description,
            priority=priority,
            dependencies=dependencies or [],
        )
        self.tasks[task.id] = task
        return task

    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """Assign a task to an agent."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        task.assigned_to = agent_id
        return True

    def get_ready_tasks(self) -> list[Task]:
        """Get tasks that are ready to execute (dependencies met)."""
        ready = []

        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue

            if task.assigned_to is None:
                continue

            # Check dependencies
            deps_met = all(
                self.tasks.get(dep_id) and
                self.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
            )

            if deps_met:
                ready.append(task)

        # Sort by priority
        priority_order = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
        }

        return sorted(ready, key=lambda t: priority_order.get(t.priority, 2))

    async def execute_task(
        self,
        task_id: str,
        executor: callable,
        timeout: Optional[float] = None,
    ) -> TaskResult:
        """
        Execute a task.

        Args:
            task_id: Task ID
            executor: Async function to execute
            timeout: Optional timeout

        Returns:
            TaskResult
        """
        task = self.tasks.get(task_id)
        if not task:
            return TaskResult(
                task_id=task_id,
                success=False,
                error="Task not found",
            )

        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()

        start_time = asyncio.get_event_loop().time()

        try:
            if timeout:
                result = await asyncio.wait_for(executor(task), timeout=timeout)
            else:
                result = await executor(task)

            duration = asyncio.get_event_loop().time() - start_time

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result = result

            task_result = TaskResult(
                task_id=task_id,
                success=True,
                result=result,
                agent_id=task.assigned_to,
                duration=duration,
            )

        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = "Task timed out"
            task_result = TaskResult(
                task_id=task_id,
                success=False,
                error="Task timed out",
                agent_id=task.assigned_to,
            )

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task_result = TaskResult(
                task_id=task_id,
                success=False,
                error=str(e),
                agent_id=task.assigned_to,
            )

        self._results[task_id] = task_result

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(task, task_result)
            except Exception as e:
                logger.warning("callback_failed", error=str(e))

        return task_result

    async def execute_all(
        self,
        executor: callable,
        max_concurrent: int = 5,
    ) -> list[TaskResult]:
        """Execute all ready tasks."""
        ready_tasks = self.get_ready_tasks()
        results = []

        # Limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_semaphore(task: Task):
            async with semaphore:
                return await self.execute_task(task.id, executor)

        results = await asyncio.gather(
            *[execute_with_semaphore(t) for t in ready_tasks],
            return_exceptions=True,
        )

        return [r if isinstance(r, TaskResult) else TaskResult(
            task_id="unknown",
            success=False,
            error=str(r),
        ) for r in results]

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get task status."""
        task = self.tasks.get(task_id)
        return task.status if task else None

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return False

        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.utcnow()
        return True

    def add_callback(self, callback: callable) -> None:
        """Add a result callback."""
        self._callbacks.append(callback)

    def get_stats(self) -> dict[str, Any]:
        """Get collaboration statistics."""
        by_status = {}
        for task in self.tasks.values():
            status = task.status.value
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total_tasks": len(self.tasks),
            "by_status": by_status,
            "total_results": len(self._results),
        }
