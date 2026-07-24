"""
Task Queue

Priority queue implementation for task scheduling.
"""

from __future__ import annotations

import heapq
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.task_manager.executor import Task, TaskPriority, TaskState


@dataclass
class QueueItem:
    """An item in the priority queue."""
    priority: int
    task: Task
    inserted_at: datetime = field(default_factory=datetime.utcnow)
    sequence: int = 0  # Tie-breaker for same priority

    def __lt__(self, other: QueueItem) -> bool:
        """Compare by priority, then by insertion time."""
        if self.priority != other.priority:
            return self.priority > other.priority  # Higher priority first
        if self.inserted_at != other.inserted_at:
            return self.inserted_at < other.inserted_at  # Earlier first
        return self.sequence < other.sequence


class TaskQueue:
    """
    Priority queue for task scheduling.

    Features:
    - Priority-based ordering
    - FIFO ordering within same priority
    - O(log n) insert and extract
    - Size tracking and limits
    """

    def __init__(self, max_size: Optional[int] = None):
        self._heap: list[QueueItem] = []
        self._task_map: dict[str, QueueItem] = {}
        self._sequence: int = 0
        self._max_size = max_size
        self._lock_count = 0

    def enqueue(self, task: Task) -> bool:
        """
        Add a task to the queue.

        Args:
            task: Task to enqueue

        Returns:
            True if added, False if queue is full
        """
        if self._max_size and len(self._heap) >= self._max_size:
            return False

        self._sequence += 1
        item = QueueItem(
            priority=task.priority.value,
            task=task,
            sequence=self._sequence,
        )

        heapq.heappush(self._heap, item)
        self._task_map[task.id] = item
        task.state = TaskState.QUEUED

        return True

    def dequeue(self) -> Optional[Task]:
        """
        Remove and return the highest priority task.

        Returns:
            Task or None if queue is empty
        """
        while self._heap:
            item = heapq.heappop(self._heap)
            if item.task.id in self._task_map:
                del self._task_map[item.task.id]
                return item.task

        return None

    def peek(self) -> Optional[Task]:
        """
        Get the highest priority task without removing it.

        Returns:
            Task or None if queue is empty
        """
        if not self._heap:
            return None

        # Find first non-locked item
        for item in self._heap:
            if item.task.id in self._task_map:
                return item.task

        return None

    def remove(self, task_id: str) -> bool:
        """
        Remove a specific task from the queue.

        Args:
            task_id: ID of task to remove

        Returns:
            True if removed, False if not found
        """
        if task_id not in self._task_map:
            return False

        del self._task_map[task_id]

        # Rebuild heap without the item (expensive but necessary)
        self._heap = [item for item in self._heap if item.task.id != task_id]
        heapq.heapify(self._heap)

        return True

    def reprioritize(self, task_id: str, new_priority: TaskPriority) -> bool:
        """
        Change the priority of a queued task.

        Args:
            task_id: Task ID
            new_priority: New priority level

        Returns:
            True if updated, False if not found
        """
        if task_id not in self._task_map:
            return False

        # Remove and re-add with new priority
        item = self._task_map[task_id]
        del self._task_map[task_id]

        self._heap = [i for i in self._heap if i.task.id != task_id]
        heapq.heapify(self._heap)

        item.priority = new_priority.value
        heapq.heappush(self._heap, item)
        self._task_map[task_id] = item

        return True

    def contains(self, task_id: str) -> bool:
        """Check if a task is in the queue."""
        return task_id in self._task_map

    def __len__(self) -> int:
        """Get number of items in queue."""
        return len(self._heap)

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._heap) == 0

    def is_full(self) -> bool:
        """Check if queue is at capacity."""
        if self._max_size is None:
            return False
        return len(self._heap) >= self._max_size

    def get_tasks(self) -> list[Task]:
        """Get all tasks in priority order."""
        return [item.task for item in sorted(self._heap, reverse=True)]

    def clear(self) -> None:
        """Remove all items from queue."""
        self._heap.clear()
        self._task_map.clear()
