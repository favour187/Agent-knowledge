"""
Task Scheduler

Schedules and manages task execution with priority queuing,
resource allocation, and parallel execution support.
"""

from __future__ import annotations

import asyncio
import heapq
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

import structlog

from core.planning_engine.planner import TaskStep, TaskStatus

logger = structlog.get_logger(__name__)


class ResourceType(str, Enum):
    """Types of resources for scheduling."""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    GPU = "gpu"
    STORAGE = "storage"
    CUSTOM = "custom"


@dataclass
class Resource:
    """A schedulable resource."""
    id: str
    type: ResourceType
    capacity: float
    available: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def allocate(self, amount: float) -> bool:
        """Allocate resources."""
        if self.available >= amount:
            self.available -= amount
            return True
        return False

    def release(self, amount: float) -> None:
        """Release resources."""
        self.available = min(self.capacity, self.available + amount)


@dataclass 
class ScheduledTask:
    """A task scheduled for execution."""
    task: TaskStep
    scheduled_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    resources: dict[str, float] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None
    priority_override: Optional[int] = None

    @property
    def effective_priority(self) -> int:
        """Calculate effective priority."""
        base = self.task.priority.value if hasattr(self.task, 'priority') else 2
        return self.priority_override or base

    @property
    def duration(self) -> timedelta:
        """Calculate task duration."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return timedelta()

    @property
    def is_ready(self) -> bool:
        """Check if task dependencies are satisfied."""
        # This would check against completed tasks
        return True


@dataclass
class Schedule:
    """An execution schedule."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tasks: list[ScheduledTask] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration: timedelta = field(default_factory=timedelta)
    resources_used: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def get_ready_tasks(self) -> list[ScheduledTask]:
        """Get tasks ready to execute."""
        ready = []
        for st in self.tasks:
            if st.started_at or st.completed_at:
                continue
            if st.is_ready:
                ready.append(st)
        return sorted(ready, key=lambda t: t.effective_priority, reverse=True)


class TaskScheduler:
    """
    Intelligent task scheduler with resource management.
    
    Features:
    - Priority-based scheduling
    - Resource allocation
    - Parallel execution support
    - Dependency management
    - Load balancing
    """

    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent
        self.resources: dict[str, Resource] = {}
        self.schedules: dict[str, Schedule] = {}
        self._active_tasks: dict[str, ScheduledTask] = {}
        self._completed_tasks: dict[str, ScheduledTask] = {}
        self._waiting_tasks: list[ScheduledTask] = []
        self._lock = asyncio.Lock()
        self._executor: Optional[asyncio.Task] = None
        self._callbacks: list[Callable[[str, ScheduledTask], Awaitable[None]]] = []

    def add_resource(self, resource: Resource) -> None:
        """Add a schedulable resource."""
        self.resources[resource.id] = resource
        logger.debug("resource_added", resource_id=resource.id, type=resource.type.value)

    def remove_resource(self, resource_id: str) -> bool:
        """Remove a resource."""
        if resource_id in self.resources:
            del self.resources[resource_id]
            return True
        return False

    def get_available_resources(
        self,
        resource_type: Optional[ResourceType] = None,
    ) -> list[Resource]:
        """Get available resources of a specific type."""
        resources = list(self.resources.values())
        if resource_type:
            resources = [r for r in resources if r.type == resource_type]
        return [r for r in resources if r.available > 0]

    def create_schedule(self, tasks: list[TaskStep]) -> Schedule:
        """Create a schedule from tasks."""
        schedule = Schedule()
        
        for task in tasks:
            st = ScheduledTask(
                task=task,
                scheduled_at=datetime.utcnow(),
            )
            schedule.tasks.append(st)
        
        self.schedules[schedule.id] = schedule
        logger.info("schedule_created", schedule_id=schedule.id, task_count=len(tasks))
        
        return schedule

    async def schedule_task(
        self,
        task: TaskStep,
        priority: Optional[int] = None,
        resources_needed: Optional[dict[str, float]] = None,
        dependencies: Optional[list[str]] = None,
    ) -> ScheduledTask:
        """Schedule a single task for execution."""
        async with self._lock:
            st = ScheduledTask(
                task=task,
                scheduled_at=datetime.utcnow(),
                resources=resources_needed or {},
                dependencies=dependencies or [],
                priority_override=priority,
            )
            
            # Try to allocate resources
            allocated = self._allocate_resources(st)
            if allocated:
                self._waiting_tasks.append(st)
                self._sort_waiting()
            else:
                # Add to schedule for later
                schedule = self.create_schedule([task])
                schedule.tasks[0] = st
            
            logger.debug(
                "task_scheduled",
                task_id=task.id,
                priority=st.effective_priority,
            )
            
            return st

    def _allocate_resources(self, task: ScheduledTask) -> bool:
        """Attempt to allocate resources for a task."""
        for resource_id, amount in task.resources.items():
            resource = self.resources.get(resource_id)
            if not resource or not resource.allocate(amount):
                # Rollback
                for rid, amt in task.resources.items():
                    if rid in self.resources:
                        self.resources[rid].release(amt)
                return False
        return True

    def _release_resources(self, task: ScheduledTask) -> None:
        """Release resources held by a task."""
        for resource_id, amount in task.resources.items():
            resource = self.resources.get(resource_id)
            if resource:
                resource.release(amount)

    def _sort_waiting(self) -> None:
        """Sort waiting tasks by priority."""
        heapq.sort(
            self._waiting_tasks,
            key=lambda t: (-t.effective_priority, t.scheduled_at),
        )

    async def start(self) -> None:
        """Start the scheduler execution loop."""
        if self._executor and not self._executor.done():
            return
        
        self._executor = asyncio.create_task(self._execution_loop())
        logger.info("scheduler_started", max_concurrent=self.max_concurrent)

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._executor:
            self._executor.cancel()
            try:
                await self._executor
            except asyncio.CancelledError:
                pass
        logger.info("scheduler_stopped")

    async def _execution_loop(self) -> None:
        """Main execution loop."""
        while True:
            try:
                await asyncio.sleep(0.1)  # 100ms tick
                
                async with self._lock:
                    # Check for completed tasks
                    completed = []
                    for task_id, task in list(self._active_tasks.items()):
                        # In real implementation, check if the actual execution completed
                        pass
                    
                    # Start new tasks if capacity allows
                    while (
                        len(self._active_tasks) < self.max_concurrent
                        and self._waiting_tasks
                    ):
                        task = self._waiting_tasks.pop(0)
                        task.started_at = datetime.utcnow()
                        self._active_tasks[task.task.id] = task
                        
                        # Notify callbacks
                        for cb in self._callbacks:
                            asyncio.create_task(cb("started", task))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_error", error=str(e))

    async def add_callback(
        self,
        callback: Callable[[str, ScheduledTask], Awaitable[None]],
    ) -> None:
        """Add a callback for task events."""
        self._callbacks.append(callback)

    def mark_task_completed(
        self,
        task_id: str,
        result: Any = None,
    ) -> bool:
        """Mark a task as completed."""
        async def _mark():
            async with self._lock:
                task = self._active_tasks.pop(task_id, None)
                if task:
                    task.completed_at = datetime.utcnow()
                    task.result = result
                    self._completed_tasks[task_id] = task
                    self._release_resources(task)
                    
                    for cb in self._callbacks:
                        asyncio.create_task(cb("completed", task))
                    
                    logger.info(
                        "task_completed",
                        task_id=task_id,
                        duration=task.duration.total_seconds(),
                    )
                    return True
                return False
        
        asyncio.create_task(_mark())
        return True

    def mark_task_failed(self, task_id: str, error: str) -> bool:
        """Mark a task as failed."""
        async def _mark():
            async with self._lock:
                task = self._active_tasks.pop(task_id, None)
                if task:
                    task.completed_at = datetime.utcnow()
                    task.error = error
                    self._completed_tasks[task_id] = task
                    self._release_resources(task)
                    
                    for cb in self._callbacks:
                        asyncio.create_task(cb("failed", task))
                    
                    logger.error("task_failed", task_id=task_id, error=error)
                    return True
                return False
        
        asyncio.create_task(_mark())
        return True

    def get_active_tasks(self) -> list[ScheduledTask]:
        """Get currently running tasks."""
        return list(self._active_tasks.values())

    def get_waiting_tasks(self) -> list[ScheduledTask]:
        """Get tasks waiting to execute."""
        return self._waiting_tasks.copy()

    def get_completed_tasks(self) -> list[ScheduledTask]:
        """Get completed tasks."""
        return list(self._completed_tasks.values())

    def get_resource_utilization(self) -> dict[str, float]:
        """Get resource utilization percentages."""
        utilization = {}
        for resource in self.resources.values():
            pct = ((resource.capacity - resource.available) / resource.capacity) * 100
            utilization[resource.id] = pct
        return utilization

    def optimize_schedule(self, schedule_id: str) -> Optional[Schedule]:
        """Optimize a schedule for better resource utilization."""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return None

        # Simple optimization: reorder tasks for better resource utilization
        tasks = sorted(schedule.tasks, key=lambda t: t.effective_priority, reverse=True)
        
        # Try to find parallelization opportunities
        for i, task in enumerate(tasks):
            for j, other in enumerate(tasks[i+1:], i+1):
                if not set(task.resources.keys()) & set(other.resources.keys()):
                    # These tasks don't share resources - could run in parallel
                    logger.debug(
                        "parallel_opportunity",
                        task1=task.task.id,
                        task2=other.task.id,
                    )

        schedule.tasks = tasks
        return schedule
