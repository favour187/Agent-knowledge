"""
Planning Engine

Breaks down complex goals into executable task plans with dependency
management, time estimation, and adaptive planning.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import structlog

from core.ai_runtime.engine import AIRuntime, Message, MessageRole

logger = structlog.get_logger(__name__)


class TaskStatus(str, Enum):
    """Status of a planned task."""
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskPriority(int, Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TaskStep:
    """
    A single step in a task plan.
    
    Attributes:
        id: Unique identifier for the step
        title: Human-readable title
        description: Detailed description of what to do
        status: Current execution status
        priority: Task priority
        dependencies: IDs of tasks that must complete first
        depends_on: Tasks that depend on this one
        estimated_duration: Estimated time in seconds
        actual_duration: Actual time taken
        result: Execution result
        error: Error message if failed
        metadata: Additional metadata
        created_at: When the step was created
        started_at: When execution started
        completed_at: When execution completed
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    dependencies: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    estimated_duration: int = 300  # 5 minutes default
    actual_duration: int = 0
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "depends_on": self.depends_on,
            "estimated_duration": self.estimated_duration,
            "actual_duration": self.actual_duration,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskStep:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            status=TaskStatus(data["status"]),
            priority=TaskPriority(data["priority"]),
            dependencies=data.get("dependencies", []),
            depends_on=data.get("depends_on", []),
            estimated_duration=data.get("estimated_duration", 300),
            actual_duration=data.get("actual_duration", 0),
            result=data.get("result"),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class Plan:
    """
    A complete task plan with multiple steps.
    
    Attributes:
        id: Unique identifier
        goal: The overall goal being planned
        steps: Ordered list of task steps
        status: Overall plan status
        progress: Progress percentage (0-100)
        estimated_duration: Total estimated time
        actual_duration: Total actual time
        created_at: When the plan was created
        updated_at: When the plan was last updated
        completed_at: When the plan was completed
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    status: str = "planning"  # planning, ready, executing, completed, failed
    progress: float = 0.0
    estimated_duration: int = 0
    actual_duration: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "progress": self.progress,
            "estimated_duration": self.estimated_duration,
            "actual_duration": self.actual_duration,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            goal=data["goal"],
            steps=[TaskStep.from_dict(s) for s in data.get("steps", [])],
            status=data.get("status", "planning"),
            progress=data.get("progress", 0.0),
            estimated_duration=data.get("estimated_duration", 0),
            actual_duration=data.get("actual_duration", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            metadata=data.get("metadata", {}),
        )

    def get_step(self, step_id: str) -> Optional[TaskStep]:
        """Get a step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_ready_steps(self) -> list[TaskStep]:
        """Get steps that are ready to execute (dependencies met)."""
        ready = []
        for step in self.steps:
            if step.status != TaskStatus.PENDING:
                continue
            deps_completed = all(
                self.get_step(dep_id).status == TaskStatus.COMPLETED
                for dep_id in step.dependencies
            )
            if deps_completed:
                ready.append(step)
        return ready

    def get_next_step(self) -> Optional[TaskStep]:
        """Get the next step to execute (highest priority ready step)."""
        ready = self.get_ready_steps()
        if not ready:
            return None
        return max(ready, key=lambda s: s.priority.value)

    def update_progress(self) -> None:
        """Update plan progress based on step statuses."""
        if not self.steps:
            self.progress = 0.0
            return
        
        total = len(self.steps)
        completed = sum(1 for s in self.steps if s.status == TaskStatus.COMPLETED)
        failed = sum(1 for s in self.steps if s.status == TaskStatus.FAILED)
        self.progress = (completed / total) * 100
        
        if failed > 0 and completed + failed == total:
            self.status = "failed"
        elif completed == total:
            self.status = "completed"
            self.completed_at = datetime.utcnow()
        
        self.updated_at = datetime.utcnow()

    def calculate_duration(self) -> int:
        """Calculate estimated duration from steps."""
        return sum(s.estimated_duration for s in self.steps)


class PlanningEngine:
    """
    AI-powered task planning engine.

    Analyzes goals, decomposes them into executable steps, manages
    dependencies, and adapts plans based on execution results.
    """

    def __init__(self, ai_runtime: Optional[AIRuntime] = None):
        self.ai_runtime = ai_runtime
        self.plans: dict[str, Plan] = {}
        self._planner_prompt = """You are an expert task planner. Your job is to break down complex goals into clear, executable steps.

Given a goal, you must:
1. Identify the key objectives
2. Break down into sequential steps that can be executed
3. Identify dependencies between steps
4. Estimate time for each step
5. Consider potential risks and edge cases

Output your plan as a JSON object with this structure:
{
    "title": "Brief title for the goal",
    "steps": [
        {
            "title": "Step title",
            "description": "Detailed description of what to do",
            "priority": 1-4 (1=low, 4=critical),
            "dependencies": ["step_id"] (if any),
            "estimated_duration": seconds,
            "risks": ["potential issue 1"]
        }
    ]
}

Be thorough but concise. Focus on actionable steps."""

    def create_plan(self, goal: str) -> Plan:
        """Create a new plan for a goal."""
        plan = Plan(goal=goal)
        self.plans[plan.id] = plan
        logger.info("plan_created", plan_id=plan.id, goal=goal)
        return plan

    def add_step(self, plan_id: str, step: TaskStep) -> Optional[TaskStep]:
        """Add a step to a plan."""
        plan = self.plans.get(plan_id)
        if not plan:
            return None
        
        plan.steps.append(step)
        plan.estimated_duration = plan.calculate_duration()
        plan.updated_at = datetime.utcnow()
        
        # Update dependency tracking
        for dep_id in step.dependencies:
            dep_step = plan.get_step(dep_id)
            if dep_step and step.id not in dep_step.depends_on:
                dep_step.depends_on.append(step.id)
        
        logger.info("step_added", plan_id=plan_id, step_id=step.id)
        return step

    async def generate_plan(
        self,
        goal: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Plan:
        """
        Generate a plan using AI.

        Args:
            goal: The goal to plan for
            context: Optional context information

        Returns:
            Generated Plan
        """
        plan = self.create_plan(goal)

        if not self.ai_runtime:
            # Create a basic single-step plan
            step = TaskStep(
                title="Execute goal",
                description=goal,
            )
            self.add_step(plan.id, step)
            return plan

        # Build context message
        context_text = ""
        if context:
            context_text = "\n\nContext:\n" + json.dumps(context, indent=2)

        messages = [
            Message(role=MessageRole.SYSTEM, content=self._planner_prompt),
            Message(
                role=MessageRole.USER,
                content=f"Goal: {goal}{context_text}\n\nGenerate a detailed plan:"
            ),
        ]

        try:
            response = await self.ai_runtime.complete(
                messages=messages,
                model="gpt-4-turbo-preview",
            )

            # Parse the response
            try:
                plan_data = json.loads(response.content)
                plan.metadata["raw_response"] = response.content
                
                if "title" in plan_data:
                    plan.metadata["title"] = plan_data["title"]

                # Convert to steps
                step_map = {}  # title -> id for dependency resolution
                for i, step_data in enumerate(plan_data.get("steps", [])):
                    step_id = f"step_{i+1}"
                    step = TaskStep(
                        id=step_id,
                        title=step_data.get("title", f"Step {i+1}"),
                        description=step_data.get("description", ""),
                        priority=TaskPriority(step_data.get("priority", 2)),
                        estimated_duration=step_data.get("estimated_duration", 300),
                        metadata={"risks": step_data.get("risks", [])},
                    )
                    plan.steps.append(step)
                    step_map[step.title.lower()] = step_id

                # Resolve dependencies by title
                for step in plan.steps:
                    resolved_deps = []
                    for dep_title in step.metadata.get("dependencies", []):
                        dep_id = step_map.get(dep_title.lower())
                        if dep_id:
                            resolved_deps.append(dep_id)
                    step.dependencies = resolved_deps

                # Update dependency tracking
                for step in plan.steps:
                    for dep_id in step.dependencies:
                        dep_step = plan.get_step(dep_id)
                        if dep_step and step.id not in dep_step.depends_on:
                            dep_step.depends_on.append(step.id)

                plan.estimated_duration = plan.calculate_duration()
                plan.status = "ready"

                logger.info(
                    "plan_generated",
                    plan_id=plan.id,
                    step_count=len(plan.steps),
                )

            except json.JSONDecodeError as e:
                logger.warning("failed_to_parse_plan", error=str(e))
                # Create fallback single step
                step = TaskStep(
                    title="Execute goal",
                    description=goal,
                )
                self.add_step(plan.id, step)

        except Exception as e:
            logger.error("plan_generation_failed", error=str(e))
            plan.status = "failed"

        return plan

    def mark_step_started(self, plan_id: str, step_id: str) -> bool:
        """Mark a step as started."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        
        step = plan.get_step(step_id)
        if not step:
            return False
        
        step.status = TaskStatus.IN_PROGRESS
        step.started_at = datetime.utcnow()
        plan.status = "executing"
        plan.updated_at = datetime.utcnow()
        
        logger.info("step_started", plan_id=plan_id, step_id=step_id)
        return True

    def mark_step_completed(
        self,
        plan_id: str,
        step_id: str,
        result: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Mark a step as completed."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        
        step = plan.get_step(step_id)
        if not step:
            return False
        
        step.status = TaskStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.result = result
        
        if step.started_at:
            step.actual_duration = int(
                (step.completed_at - step.started_at).total_seconds()
            )
        
        plan.update_progress()
        plan.actual_duration = sum(s.actual_duration for s in plan.steps)
        
        logger.info(
            "step_completed",
            plan_id=plan_id,
            step_id=step_id,
            actual_duration=step.actual_duration,
        )
        return True

    def mark_step_failed(
        self,
        plan_id: str,
        step_id: str,
        error: str,
    ) -> bool:
        """Mark a step as failed."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        
        step = plan.get_step(step_id)
        if not step:
            return False
        
        step.status = TaskStatus.FAILED
        step.completed_at = datetime.utcnow()
        step.error = error
        
        if step.started_at:
            step.actual_duration = int(
                (step.completed_at - step.started_at).total_seconds()
            )
        
        plan.update_progress()
        
        logger.error(
            "step_failed",
            plan_id=plan_id,
            step_id=step_id,
            error=error,
        )
        return True

    def skip_step(self, plan_id: str, step_id: str, reason: str) -> bool:
        """Skip a step with a reason."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        
        step = plan.get_step(step_id)
        if not step:
            return False
        
        step.status = TaskStatus.SKIPPED
        step.completed_at = datetime.utcnow()
        step.error = reason
        
        plan.update_progress()
        
        logger.info(
            "step_skipped",
            plan_id=plan_id,
            step_id=step_id,
            reason=reason,
        )
        return True

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        """Get a plan by ID."""
        return self.plans.get(plan_id)

    def list_plans(self, status: Optional[str] = None) -> list[Plan]:
        """List all plans, optionally filtered by status."""
        plans = list(self.plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        return sorted(plans, key=lambda p: p.created_at, reverse=True)

    async def revise_plan(
        self,
        plan_id: str,
        failure_reason: str,
    ) -> Optional[Plan]:
        """
        Revise a failed plan based on failure analysis.

        Args:
            plan_id: Plan to revise
            failure_reason: Why the original plan failed

        Returns:
            Revised plan or None
        """
        plan = self.plans.get(plan_id)
        if not plan:
            return None

        if not self.ai_runtime:
            return plan

        revision_prompt = f"""The following plan failed to achieve its goal:

Goal: {plan.goal}

Original Steps:
{json.dumps([s.to_dict() for s in plan.steps], indent=2)}

Failure Reason: {failure_reason}

Create a revised plan that addresses the failure and successfully achieves the goal:"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=self._planner_prompt),
            Message(role=MessageRole.USER, content=revision_prompt),
        ]

        try:
            response = await self.ai_runtime.complete(
                messages=messages,
                model="gpt-4-turbo-preview",
            )

            # Parse and update plan
            try:
                plan_data = json.loads(response.content)
                
                # Clear non-completed steps
                for step in plan.steps:
                    if step.status not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
                        step.status = TaskStatus.PENDING
                        step.error = None
                        step.started_at = None
                        step.completed_at = None

                # Add new steps if any
                for i, step_data in enumerate(plan_data.get("steps", [])):
                    step = TaskStep(
                        title=step_data.get("title", f"New Step {i+1}"),
                        description=step_data.get("description", ""),
                        priority=TaskPriority(step_data.get("priority", 2)),
                        estimated_duration=step_data.get("estimated_duration", 300),
                        metadata={"risks": step_data.get("risks", [])},
                    )
                    self.add_step(plan.id, step)

                plan.metadata["revision_count"] = plan.metadata.get("revision_count", 0) + 1
                plan.metadata["last_revision_reason"] = failure_reason

                logger.info(
                    "plan_revised",
                    plan_id=plan_id,
                    revision_count=plan.metadata["revision_count"],
                )

            except json.JSONDecodeError:
                logger.warning("failed_to_parse_revision")

        except Exception as e:
            logger.error("plan_revision_failed", error=str(e))

        return plan
