"""
Agent

An autonomous AI agent with memory, tools, and planning capabilities.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from core.ai_runtime.engine import AIRuntime, Message as AIMessage, MessageRole
from core.memory_manager.manager import MemoryManager
from core.tool_manager.registry import ToolRegistry
from core.planning_engine.planner import PlanningEngine, Plan
from core.reasoning_engine.reasoner import ReasoningEngine, ReasoningStrategy

logger = structlog.get_logger(__name__)


class AgentState(str, Enum):
    """Agent lifecycle states."""
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING = "waiting"
    ERROR = "error"
    STOPPED = "stopped"


class MessageRole(str, Enum):
    """Roles for agent messages."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    AGENT = "agent"


@dataclass
class Message:
    """A message in agent communication."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: MessageRole = MessageRole.USER
    content: str = ""
    sender_id: Optional[str] = None
    recipient_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None

    def to_ai_message(self) -> AIMessage:
        """Convert to AI runtime message."""
        return AIMessage(
            role=MessageRole(self.role.value),
            content=self.content,
            name=self.metadata.get("name"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "reply_to": self.reply_to,
        }


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str = "Assistant"
    description: str = ""
    system_prompt: str = """You are a helpful AI assistant. 
You have access to various tools to help users accomplish tasks.
Think step by step and use tools when appropriate.
Always explain your reasoning."""
    model: str = "gpt-4-turbo-preview"
    temperature: float = 0.7
    max_tokens: int = 4096
    max_context_messages: int = 50
    tools_enabled: bool = True
    memory_enabled: bool = True
    planning_enabled: bool = True
    reasoning_enabled: bool = True
    reasoning_strategy: ReasoningStrategy = ReasoningStrategy.CHAIN_OF_THOUGHT
    tools: list[str] = field(default_factory=list)  # Tool names to enable
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Agent:
    """
    An autonomous AI agent.

    Features:
    - Natural language understanding and generation
    - Tool use and execution
    - Persistent memory
    - Task planning
    - Multi-step reasoning
    - Session management
    """

    def __init__(
        self,
        config: AgentConfig,
        ai_runtime: Optional[AIRuntime] = None,
        tool_registry: Optional[ToolRegistry] = None,
        memory_manager: Optional[MemoryManager] = None,
    ):
        self.id = str(uuid.uuid4())
        self.config = config
        self.state = AgentState.IDLE

        # Core components
        self.ai_runtime = ai_runtime
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager

        # Planning and reasoning
        self.planning_engine = PlanningEngine(ai_runtime) if config.planning_enabled else None
        self.reasoning_engine = ReasoningEngine(ai_runtime) if config.reasoning_enabled else None

        # Session state
        self.messages: list[Message] = []
        self.current_plan: Optional[Plan] = None
        self._running = False
        self._lock = asyncio.Lock()

        # Callbacks
        self._on_message: Optional[Callable[[Message], None]] = None
        self._on_state_change: Optional[Callable[[AgentState, AgentState], None]] = None
        self._on_error: Optional[Callable[[Exception], None]] = None

        logger.info("agent_created", agent_id=self.id, name=config.name)

    @property
    def name(self) -> str:
        """Get agent name."""
        return self.config.name

    @property
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self._running

    def set_message_callback(self, callback: Callable[[Message], None]) -> None:
        """Set callback for incoming messages."""
        self._on_message = callback

    def set_state_callback(
        self,
        callback: Callable[[AgentState, AgentState], None],
    ) -> None:
        """Set callback for state changes."""
        self._on_state_change = callback

    def set_error_callback(self, callback: Callable[[Exception], None]) -> None:
        """Set callback for errors."""
        self._on_error = callback

    def _update_state(self, new_state: AgentState) -> None:
        """Update agent state with callback."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.debug(
                "agent_state_changed",
                agent_id=self.id,
                from_state=old_state.value,
                to_state=new_state.value,
            )
            if self._on_state_change:
                self._on_state_change(old_state, new_state)

    async def start(self) -> None:
        """Start the agent."""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._update_state(AgentState.IDLE)
            logger.info("agent_started", agent_id=self.id)

    async def stop(self) -> None:
        """Stop the agent."""
        async with self._lock:
            self._running = False
            self._update_state(AgentState.STOPPED)
            logger.info("agent_stopped", agent_id=self.id)

    async def think(self, prompt: str) -> str:
        """
        Have the agent think about a problem without acting.

        Args:
            prompt: The problem or question to think about

        Returns:
            Thinking result
        """
        if not self.ai_runtime:
            return "AI runtime not configured"

        self._update_state(AgentState.THINKING)

        if self.reasoning_engine:
            result = await self.reasoning_engine.reason(
                problem=prompt,
                strategy=self.config.reasoning_strategy,
            )
            return result.answer

        # Simple completion
        messages = [
            AIMessage(role=MessageRole.SYSTEM, content=self.config.system_prompt),
            AIMessage(role=MessageRole.USER, content=prompt),
        ]

        response = await self.ai_runtime.complete(
            messages=messages,
            model=self.config.model,
        )

        self._update_state(AgentState.IDLE)
        return response.content

    async def act(self, goal: str) -> dict[str, Any]:
        """
        Have the agent act to achieve a goal.

        Args:
            goal: The goal to achieve

        Returns:
            Result of the action
        """
        if not self.ai_runtime:
            return {"success": False, "error": "AI runtime not configured"}

        async with self._lock:
            if not self._running:
                return {"success": False, "error": "Agent not running"}

        self._update_state(AgentState.ACTING)

        try:
            # Generate plan if planning enabled
            if self.planning_engine:
                self.current_plan = await self.planning_engine.generate_plan(goal)
                
                # Execute plan steps
                for step in self.current_plan.steps:
                    self._update_state(AgentState.ACTING)
                    self.planning_engine.mark_step_started(self.current_plan.id, step.id)

                    # Execute the step
                    result = await self._execute_step(step.description)

                    if result["success"]:
                        self.planning_engine.mark_step_completed(
                            self.current_plan.id, step.id, result
                        )
                    else:
                        self.planning_engine.mark_step_failed(
                            self.current_plan.id, step.id, result.get("error", "Unknown")
                        )
                        return result

                return {
                    "success": True,
                    "result": result,
                    "plan": self.current_plan.to_dict(),
                }
            else:
                # Direct execution without planning
                return await self._execute_step(goal)

        except Exception as e:
            logger.error("agent_act_failed", agent_id=self.id, error=str(e))
            self._update_state(AgentState.ERROR)
            if self._on_error:
                self._on_error(e)
            return {"success": False, "error": str(e)}

        finally:
            self._update_state(AgentState.IDLE)

    async def _execute_step(self, instruction: str) -> dict[str, Any]:
        """Execute a single step."""
        if not self.ai_runtime:
            return {"success": False, "error": "AI runtime not configured"}

        # Build messages
        messages = [
            AIMessage(role=MessageRole.SYSTEM, content=self.config.system_prompt),
        ]

        # Add conversation history
        for msg in self.messages[-self.config.max_context_messages:]:
            messages.append(msg.to_ai_message())

        messages.append(AIMessage(role=MessageRole.USER, content=instruction))

        # Get tools if enabled
        tools = None
        if self.config.tools_enabled and self.tool_registry:
            tools = self.tool_registry.get_tool_schemas(
                names=self.config.tools if self.config.tools else None
            )

        # Execute with tool support
        response = await self.ai_runtime.complete(
            messages=messages,
            model=self.config.model,
            tools=tools,
        )

        # Handle tool calls
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_result = await self._execute_tool(
                    tool_call.name,
                    tool_call.arguments,
                )

                # Add tool result to messages
                messages.append(
                    AIMessage(
                        role=MessageRole.TOOL,
                        content=str(tool_result),
                        tool_call_id=tool_call.id,
                    )
                )

            # Get final response with tool results
            response = await self.ai_runtime.complete(
                messages=messages,
                model=self.config.model,
            )

        return {
            "success": True,
            "response": response.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Execute a tool."""
        if not self.tool_registry:
            return {"error": "Tool registry not available"}

        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return {"error": f"Tool not found: {tool_name}"}

        try:
            result = await tool.execute(**arguments)
            return result
        except Exception as e:
            logger.error("tool_execution_failed", tool=tool_name, error=str(e))
            return {"error": str(e)}

    async def chat(self, user_message: str) -> str:
        """
        Have a conversation with the agent.

        Args:
            user_message: User's message

        Returns:
            Agent's response
        """
        # Add user message
        user_msg = Message(
            role=MessageRole.USER,
            content=user_message,
        )
        self.messages.append(user_msg)

        # Get response
        result = await self.act(user_message)

        if result["success"]:
            response_content = result.get("response", "")
        else:
            response_content = f"I encountered an error: {result.get('error')}"

        # Add assistant message
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response_content,
        )
        self.messages.append(assistant_msg)

        # Store in memory if enabled
        if self.memory_manager and self.config.memory_enabled:
            await self.memory_manager.add_memory(
                content=f"User: {user_message}\nAssistant: {response_content}",
                memory_type="episodic",
                agent_id=self.id,
            )

        return response_content

    async def remember(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Query the agent's memory.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of relevant memories
        """
        if not self.memory_manager:
            return []

        return await self.memory_manager.search_memory(
            query=query,
            agent_id=self.id,
            limit=limit,
        )

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        logger.info("agent_history_cleared", agent_id=self.id)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.config.name,
            "description": self.config.description,
            "state": self.state.value,
            "message_count": len(self.messages),
            "config": {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "tools_enabled": self.config.tools_enabled,
                "memory_enabled": self.config.memory_enabled,
                "planning_enabled": self.config.planning_enabled,
            },
            "created_at": datetime.utcnow().isoformat(),
        }
