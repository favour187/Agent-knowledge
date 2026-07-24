"""Shared application state container.

Split out from api/main.py so route modules can import `app_state` directly
(api/main.py imports the route modules, so route modules importing back
from api/main.py would be a circular import).
"""

from __future__ import annotations

from typing import Optional

from core import (
    AIRuntime,
    AgentManager,
    KnowledgeBase,
    MemoryManager,
    MultiAgentOrchestrator,
    PlanningEngine,
    ReasoningEngine,
    SelfEvaluator,
    SelfImprover,
    TaskExecutor,
    ToolRegistry,
)


class AppState:
    """Application state container."""
    ai_runtime: Optional[AIRuntime] = None
    agent_manager: Optional[AgentManager] = None
    tool_registry: Optional[ToolRegistry] = None
    memory_manager: Optional[MemoryManager] = None
    knowledge_base: Optional[KnowledgeBase] = None
    planning_engine: Optional[PlanningEngine] = None
    reasoning_engine: Optional[ReasoningEngine] = None
    task_executor: Optional[TaskExecutor] = None
    multi_agent: Optional[MultiAgentOrchestrator] = None
    self_evaluator: Optional[SelfEvaluator] = None
    self_improver: Optional[SelfImprover] = None


app_state = AppState()


def get_state() -> AppState:
    """Get application state."""
    return app_state
