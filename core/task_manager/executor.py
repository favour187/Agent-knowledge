"""
Task Executor

Executes tasks with lifecycle management, retries, timeouts,
and progress tracking.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class TaskState(str, Enum):
    """Task execution states."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskPriority(int, Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Task:
    """
    An executable task with lifecycle management.
    
    Attributes:
        id: Unique identifier
        name: Task name
        description: Task description
        func: The async function to execute
        args: Positional arguments for the function
        kwargs: Keyword arguments for the function
        state: Current execution state
        priority: Task priority
        timeout: Maximum execution time in seconds
        retry_count: Number of retries attempted
        max_retries: Maximum number of retries
        created_at: When task was created
        started_at: When execution started
        completed_at: When execution completed
        result: Task result if successful
        error: Error message if failed
        progress: Progress percentage (0-100)
        metadata: Additional metadata
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    func: Optional[Callable[..., Awaitable[Any]]] = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    state: TaskState = TaskState.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    timeout: Optional[int] = None  # None = no timeout
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: float = 1.0  # Base delay between retries
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    progress: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "priority": self.priority.value,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "metadata": self.metadata,
            "tags": self.tags,
            "parent_id": self.parent_id,
            "dependencies": self.dependencies,
        }

    @property
    def duration(self) -> Optional[timedelta]:
        """Get task duration."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return datetime.utcnow() - self.started_at
        return None

    @property
    def is_active(self) -> bool:
        """Check if task is currently active."""
        return self.state in (TaskState.RUNNING, TaskState.QUEUED)

    @property
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.state in (
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
            TaskState.TIMEOUT,
        )


@dataclass
class TaskResult:
    """Result of task execution."""
    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration: Optional[float] = None
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskExecutor:
    """
    Async task executor with lifecycle management.

    Features:
    - Task creation and tracking
    - Automatic retries with backoff
    - Timeout handling
    - Progress reporting
    - Task cancellation
    - Dependency management
    - Event callbacks
    """

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.tasks: dict[str, Task] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._callbacks: dict[str, list[Callable[[Task], None]]] = {
            "created": [],
            "started": [],
            "progress": [],
            "completed": [],
            "failed": [],
            "cancelled": [],
        }
        self._semaphore = asyncio.Semaphore(max_workers)

    def create_task(
        self,
        func: Callable[..., Awaitable[Any]],
        *args: Any,
        name: Optional[str] = None,
        description: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: Optional[int] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        tags: Optional[list[str]] = None,
        parent_id: Optional[str] = None,
        dependencies: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> Task:
        """
        Create a new task.

        Args:
            func: Async function to execute
            *args: Positional arguments
            name: Task name
            description: Task description
            priority: Task priority
            timeout: Maximum execution time in seconds
            max_retries: Maximum retry attempts
            retry_delay: Base delay between retries
            tags: Task tags
            parent_id: Parent task ID
            dependencies: Task IDs that must complete first
            **kwargs: Keyword arguments

        Returns:
            Created Task
        """
        task = Task(
            name=name or func.__name__,
            description=description,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            tags=tags or [],
            parent_id=parent_id,
            dependencies=dependencies or [],
        )

        self.tasks[task.id] = task
        self._emit("created", task)

        logger.info(
            "task_created",
            task_id=task.id,
            name=task.name,
            priority=task.priority.value,
        )

        return task

    async def execute(self, task_id: str) -> TaskResult:
        """
        Execute a task.

        Args:
            task_id: Task ID to execute

        Returns:
            TaskResult
        """
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return TaskResult(
                    task_id=task_id,
                    success=False,
                    error="Task not found",
                )

            if task.state != TaskState.PENDING:
                return TaskResult(
                    task_id=task_id,
                    success=False,
                    error=f"Task already in state: {task.state.value}",
                )

            task.state = TaskState.QUEUED

        result = await self._execute_with_retry(task)

        if result.success:
            task.state = TaskState.COMPLETED
            task.result = result.result
            self._emit("completed", task)
        else:
            if "timeout" in result.error.lower():
                task.state = TaskState.TIMEOUT
            elif task.retry_count >= task.max_retries:
                task.state = TaskState.FAILED
            self._emit("failed", task)

        return result

    async def _execute_with_retry(self, task: Task) -> TaskResult:
        """Execute task with retry logic."""
        async with self._semaphore:
            task.state = TaskState.RUNNING
            task.started_at = datetime.utcnow()
            self._emit("started", task)

            attempt = 0
            last_error = None

            while attempt <= task.max_retries:
                try:
                    # Execute with timeout if specified
                    if task.timeout:
                        result = await asyncio.wait_for(
                            task.func(*task.args, **task.kwargs),
                            timeout=task.timeout,
                        )
                    else:
                        result = await task.func(*task.args, **task.kwargs)

                    duration = (datetime.utcnow() - task.started_at).total_seconds()

                    return TaskResult(
                        task_id=task.id,
                        success=True,
                        result=result,
                        duration=duration,
                        retry_count=attempt,
                    )

                except asyncio.TimeoutError:
                    last_error = f"Task timed out after {task.timeout}s"
                    logger.warning(
                        "task_timeout",
                        task_id=task.id,
                        timeout=task.timeout,
                        attempt=attempt,
                    )

                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "task_error",
                        task_id=task.id,
                        error=str(e),
                        attempt=attempt,
                    )

                attempt += 1
                task.retry_count = attempt

                if attempt <= task.max_retries:
                    # Exponential backoff
                    delay = task.retry_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

            return TaskResult(
                task_id=task.id,
                success=False,
                error=last_error or "Unknown error",
                retry_count=task.retry_count,
            )

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running task."""
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return False

            if task.state == TaskState.RUNNING:
                running_task = self._running_tasks.get(task_id)
                if running_task:
                    running_task.cancel()
                    try:
                        await running_task
                    except asyncio.CancelledError:
                        pass

            task.state = TaskState.CANCELLED
            task.completed_at = datetime.utcnow()
            self._emit("cancelled", task)

            logger.info("task_cancelled", task_id=task_id)
            return True

    def update_progress(self, task_id: str, progress: float) -> bool:
        """Update task progress."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        task.progress = max(0, min(100, progress))
        self._emit("progress", task)
        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_tasks(
        self,
        state: Optional[TaskState] = None,
        tags: Optional[list[str]] = None,
    ) -> list[Task]:
        """Get tasks filtered by state and/or tags."""
        tasks = list(self.tasks.values())

        if state:
            tasks = [t for t in tasks if t.state == state]

        if tags:
            tasks = [t for t in tasks if any(tag in t.tags for tag in tags)]

        return sorted(tasks, key=lambda t: (-t.priority.value, t.created_at))

    def get_running_tasks(self) -> list[Task]:
        """Get currently running tasks."""
        return [
            t for t in self.tasks.values()
            if t.state == TaskState.RUNNING
        ]

    def get_pending_tasks(self) -> list[Task]:
        """Get pending tasks."""
        return [
            t for t in self.tasks.values()
            if t.state == TaskState.PENDING
        ]

    def add_callback(
        self,
        event: str,
        callback: Callable[[Task], None],
    ) -> None:
        """Add an event callback."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit(self, event: str, task: Task) -> None:
        """Emit an event to callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(task)
            except Exception as e:
                logger.error("callback_error", event=event, error=str(e))

    async def execute_many(
        self,
        task_ids: list[str],
        fail_fast: bool = False,
    ) -> list[TaskResult]:
        """
        Execute multiple tasks.

        Args:
            task_ids: List of task IDs to execute
            fail_fast: Stop on first failure

        Returns:
            List of TaskResults
        """
        results = []

        for task_id in task_ids:
            result = await self.execute(task_id)
            results.append(result)

            if fail_fast and not result.success:
                break

        return results

    async def execute_parallel(
        self,
        task_ids: list[str],
    ) -> list[TaskResult]:
        """
        Execute multiple tasks in parallel.

        Args:
            task_ids: List of task IDs to execute

        Returns:
            List of TaskResults
        """
        tasks = [self.execute(tid) for tid in task_ids]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def clear_completed(self, older_than: Optional[datetime] = None) -> int:
        """Clear completed tasks from memory."""
        count = 0
        to_remove = []

        for task_id, task in self.tasks.items():
            if task.is_terminal:
                if older_than is None or (
                    task.completed_at and task.completed_at < older_than
                ):
                    to_remove.append(task_id)
                    count += 1

        for task_id in to_remove:
            del self.tasks[task_id]

        logger.info("tasks_cleared", count=count)
        return count
