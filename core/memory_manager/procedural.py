"""
Procedural Memory

Stores skills, procedures, and learned behaviors.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from core.memory_manager.manager import Memory, MemoryManager, MemoryType

logger = structlog.get_logger(__name__)


class ProcedureType(str, Enum):
    """Types of procedures."""
    ALGORITHM = "algorithm"       # Step-by-step procedure
    HEURISTIC = "heuristic"       # Rule of thumb
    SKILL = "skill"              # Learned skill
    HABIT = "habit"             # Automatic behavior
    STRATEGY = "strategy"       # Problem-solving strategy


@dataclass
class Procedure:
    """
    A stored procedure or skill.

    Attributes:
        id: Unique identifier
        name: Procedure name
        description: What the procedure does
        procedure_type: Type of procedure
        steps: Ordered steps (for algorithms)
        conditions: When to apply (for heuristics)
        context: When it's applicable
        success_rate: Historical success rate
        times_used: Number of times executed
        last_used: Last execution time
        created_at: Creation time
        updated_at: Last update time
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    procedure_type: ProcedureType = ProcedureType.ALGORITHM
    steps: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    context: str = ""
    success_rate: float = 0.0
    times_used: int = 0
    total_executions: int = 0
    last_used: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    prerequisites: list[str] = field(default_factory=list)  # Other procedure IDs
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_execution(self, success: bool) -> None:
        """Record an execution of this procedure."""
        self.total_executions += 1
        if success:
            self.success_rate = (
                (self.success_rate * (self.total_executions - 1) + 1)
                / self.total_executions
            )
        else:
            self.success_rate = (
                self.success_rate * (self.total_executions - 1)
            ) / self.total_executions
        self.times_used += 1
        self.last_used = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "procedure_type": self.procedure_type.value,
            "steps": self.steps,
            "conditions": self.conditions,
            "context": self.context,
            "success_rate": self.success_rate,
            "times_used": self.times_used,
            "total_executions": self.total_executions,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "prerequisites": self.prerequisites,
            "metadata": self.metadata,
        }


class ProceduralMemory:
    """
    Procedural memory for storing skills and procedures.

    Features:
    - Procedure storage and retrieval
    - Success rate tracking
    - Learning from experience
    - Procedure composition
    - Skill assessment
    """

    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self._procedures: dict[str, Procedure] = {}
        self._context_index: dict[str, set[str]] = {}  # context -> procedure_ids

    async def add_procedure(
        self,
        name: str,
        description: str,
        procedure_type: ProcedureType = ProcedureType.ALGORITHM,
        steps: Optional[list[str]] = None,
        conditions: Optional[list[str]] = None,
        context: str = "",
        prerequisites: Optional[list[str]] = None,
    ) -> Procedure:
        """Add a new procedure."""
        procedure = Procedure(
            name=name,
            description=description,
            procedure_type=procedure_type,
            steps=steps or [],
            conditions=conditions or [],
            context=context,
            prerequisites=prerequisites or [],
        )

        self._procedures[procedure.id] = procedure

        # Update context index
        if context:
            ctx_lower = context.lower()
            if ctx_lower not in self._context_index:
                self._context_index[ctx_lower] = set()
            self._context_index[ctx_lower].add(procedure.id)

        # Store as procedural memory
        content = f"{name}: {description}"
        if steps:
            content += "\n\nSteps:\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))

        await self.memory_manager.add_memory(
            content=content,
            memory_type=MemoryType.PROCEDURAL,
            agent_id=None,  # Shared across agents
            importance=0.7,
            tags=[procedure_type.value, "procedure", name.lower()],
            source=f"procedure:{procedure.id}",
        )

        return procedure

    def get_procedure(self, procedure_id: str) -> Optional[Procedure]:
        """Get a procedure by ID."""
        return self._procedures.get(procedure_id)

    def get_procedure_by_name(self, name: str) -> Optional[Procedure]:
        """Get a procedure by name."""
        for procedure in self._procedures.values():
            if procedure.name.lower() == name.lower():
                return procedure
        return None

    def get_procedures_for_context(self, context: str) -> list[Procedure]:
        """Get procedures applicable to a context."""
        results = []
        context_lower = context.lower()

        for procedure in self._procedures.values():
            # Check direct context match
            if procedure.context and procedure.context.lower() in context_lower:
                results.append(procedure)
                continue

            # Check context index
            for ctx_key in self._context_index:
                if ctx_key in context_lower:
                    if procedure.id in self._context_index[ctx_key]:
                        results.append(procedure)
                        break

        # Sort by success rate
        results.sort(key=lambda p: p.success_rate, reverse=True)
        return results

    def get_all_procedures(
        self,
        procedure_type: Optional[ProcedureType] = None,
        min_success_rate: float = 0.0,
    ) -> list[Procedure]:
        """Get all procedures, optionally filtered."""
        procedures = list(self._procedures.values())

        if procedure_type:
            procedures = [p for p in procedures if p.procedure_type == procedure_type]

        if min_success_rate > 0:
            procedures = [p for p in procedures if p.success_rate >= min_success_rate]

        procedures.sort(key=lambda p: p.success_rate, reverse=True)
        return procedures

    def record_execution(self, procedure_id: str, success: bool) -> bool:
        """Record an execution of a procedure."""
        procedure = self._procedures.get(procedure_id)
        if not procedure:
            return False

        procedure.record_execution(success)

        # Update memory importance based on success
        if success and procedure.success_rate > 0.8:
            asyncio.create_task(
                self.memory_manager.update_memory(
                    memory_id=f"procedure:{procedure_id}",
                    importance=procedure.success_rate * 0.8,
                )
            )

        return True

    async def learn_from_experience(
        self,
        situation: str,
        action_taken: str,
        outcome: str,
        success: bool,
    ) -> Optional[Procedure]:
        """
        Learn a new procedure from experience.

        Analyzes the experience and creates or updates a procedure.
        """
        # Check if similar procedure exists
        existing = self.get_procedure_by_name(f"{situation} -> {action_taken}")
        if existing:
            existing.record_execution(success)
            return existing

        # Create new procedure from experience
        procedure = await self.add_procedure(
            name=f"{situation} -> {action_taken}",
            description=f"When {situation}, take action: {action_taken}. Outcome: {outcome}",
            procedure_type=ProcedureType.HEURISTIC,
            conditions=[situation],
            context=situation,
        )

        procedure.record_execution(success)
        return procedure

    def get_skills(
        self,
        min_mastery: float = 0.5,
    ) -> list[Procedure]:
        """Get mastered skills (procedures with high success rate)."""
        return [
            p for p in self._procedures.values()
            if p.procedure_type == ProcedureType.SKILL
            and p.success_rate >= min_mastery
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get procedural memory statistics."""
        by_type = {}
        for procedure in self._procedures.values():
            ptype = procedure.procedure_type.value
            if ptype not in by_type:
                by_type[ptype] = {"count": 0, "avg_success": 0, "total_uses": 0}
            by_type[ptype]["count"] += 1
            by_type[ptype]["total_uses"] += procedure.total_executions

        for ptype in by_type:
            procs = [p for p in self._procedures.values() if p.procedure_type.value == ptype]
            if procs:
                by_type[ptype]["avg_success"] = sum(p.success_rate for p in procs) / len(procs)

        return {
            "total_procedures": len(self._procedures),
            "by_type": by_type,
            "total_executions": sum(p.total_executions for p in self._procedures.values()),
            "procedures_by_context": len(self._context_index),
        }
