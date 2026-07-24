"""
Arena AI Platform - Core Module

A comprehensive autonomous AI agent platform with multi-agent orchestration,
persistent memory, and advanced reasoning capabilities.
"""

__version__ = "0.1.0"
__author__ = "Arena AI Team"

# Import core components with graceful fallback if dependencies are missing.
# This allows submodules (like core.training) to be imported independently
# without requiring the full platform dependency stack.

try:
    from core.ai_runtime.engine import AIRuntime, AIProvider
except ImportError:
    AIRuntime = None  # type: ignore
    AIProvider = None  # type: ignore

try:
    from core.agent_manager.agent import Agent
except ImportError:
    Agent = None  # type: ignore

try:
    from core.agent_manager.manager import AgentManager
except ImportError:
    AgentManager = None  # type: ignore

try:
    from core.planning_engine.planner import PlanningEngine
except ImportError:
    PlanningEngine = None  # type: ignore

try:
    from core.reasoning_engine.reasoner import ReasoningEngine
except ImportError:
    ReasoningEngine = None  # type: ignore

try:
    from core.task_manager.executor import TaskExecutor, Task
except ImportError:
    TaskExecutor = None  # type: ignore
    Task = None  # type: ignore

try:
    from core.tool_manager.registry import ToolRegistry
except ImportError:
    ToolRegistry = None  # type: ignore

try:
    from core.memory_manager.manager import MemoryManager
except ImportError:
    MemoryManager = None  # type: ignore

try:
    from core.knowledge_base.manager import KnowledgeBase
except ImportError:
    KnowledgeBase = None  # type: ignore

try:
    from core.context_manager.manager import ContextManager
except ImportError:
    ContextManager = None  # type: ignore

try:
    from core.multi_agent.orchestrator import MultiAgentOrchestrator
except ImportError:
    MultiAgentOrchestrator = None  # type: ignore

try:
    from core.self_evaluation.evaluator import SelfEvaluator
except ImportError:
    SelfEvaluator = None  # type: ignore

try:
    from core.self_improvement.learner import SelfImprover
except ImportError:
    SelfImprover = None  # type: ignore

__all__ = [
    # Core runtime
    "AIRuntime",
    "AIProvider",
    # Agents
    "Agent",
    "AgentManager",
    # Engines
    "PlanningEngine",
    "ReasoningEngine",
    "TaskExecutor",
    "Task",
    # Management
    "ToolRegistry",
    "MemoryManager",
    "KnowledgeBase",
    "ContextManager",
    # Advanced
    "MultiAgentOrchestrator",
    "SelfEvaluator",
    "SelfImprover",
]
