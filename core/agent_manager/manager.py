"""
Agent Manager

Manages multiple agents, their lifecycle, and orchestration.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from core.agent_manager.agent import Agent, AgentConfig, AgentState, Message
from core.ai_runtime.engine import AIRuntime
from core.tool_manager.registry import ToolRegistry
from core.memory_manager.manager import MemoryManager

logger = structlog.get_logger(__name__)


class ManagerEvent(str, Enum):
    """Events from the agent manager."""
    AGENT_CREATED = "agent_created"
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_ERROR = "agent_error"
    AGENT_MESSAGE = "agent_message"
    AGENT_STATE_CHANGED = "agent_state_changed"


@dataclass
class ManagerEventData:
    """Data associated with a manager event."""
    event: ManagerEvent
    agent_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamConfig:
    """Configuration for a multi-agent team."""
    name: str
    description: str = ""
    roles: dict[str, str] = field(default_factory=dict)  # role -> prompt
    collaboration_mode: str = "sequential"  # sequential, parallel, hierarchical
    max_agents: int = 10


class AgentManager:
    """
    Manager for multiple AI agents.

    Features:
    - Agent lifecycle management
    - Team coordination
    - Event broadcasting
    - Resource allocation
    - Agent templates
    """

    def __init__(
        self,
        ai_runtime: Optional[AIRuntime] = None,
        tool_registry: Optional[ToolRegistry] = None,
        memory_manager: Optional[MemoryManager] = None,
    ):
        self.ai_runtime = ai_runtime
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager

        self.agents: dict[str, Agent] = {}
        self.teams: dict[str, list[str]] = {}  # team_name -> agent_ids
        self.templates: dict[str, AgentConfig] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._event_loop: Optional[asyncio.Task] = None

        # Event handlers
        self._handlers: dict[ManagerEvent, list[Callable]] = {
            event: [] for event in ManagerEvent
        }

        # Load default templates
        self._load_default_templates()

        logger.info("agent_manager_initialized")

    def _load_default_templates(self) -> None:
        """Load default agent templates."""
        self.register_template(
            name="assistant",
            config=AgentConfig(
                name="Assistant",
                description="A general-purpose AI assistant",
                system_prompt="You are a helpful, harmless, and honest AI assistant.",
            ),
        )

        self.register_template(
            name="coder",
            config=AgentConfig(
                name="Code Assistant",
                description="An AI specialized in programming",
                system_prompt="""You are an expert programmer assistant.
You have extensive knowledge of multiple programming languages, best practices, and software design patterns.
When writing code, always prioritize readability, maintainability, and efficiency.
Explain your code and reasoning clearly.""",
            ),
        )

        self.register_template(
            name="researcher",
            config=AgentConfig(
                name="Research Assistant",
                description="An AI specialized in research and analysis",
                system_prompt="""You are a meticulous research assistant.
You excel at finding information, analyzing data, and synthesizing findings.
Always cite sources and be clear about the confidence level of your conclusions.
Focus on accuracy and thoroughness.""",
            ),
        )

    def register_template(self, name: str, config: AgentConfig) -> None:
        """Register an agent template."""
        self.templates[name] = config
        logger.debug("template_registered", name=name)

    def create_template_from_config(
        self,
        name: str,
        base_template: str,
        **overrides: Any,
    ) -> AgentConfig:
        """Create a new template from an existing one with overrides."""
        if base_template not in self.templates:
            raise ValueError(f"Unknown template: {base_template}")

        base = self.templates[base_template]
        config = AgentConfig(
            name=overrides.get("name", base.name),
            description=overrides.get("description", base.description),
            system_prompt=overrides.get("system_prompt", base.system_prompt),
            model=overrides.get("model", base.model),
            temperature=overrides.get("temperature", base.temperature),
            max_tokens=overrides.get("max_tokens", base.max_tokens),
            tools_enabled=overrides.get("tools_enabled", base.tools_enabled),
            memory_enabled=overrides.get("memory_enabled", base.memory_enabled),
            planning_enabled=overrides.get("planning_enabled", base.planning_enabled),
            reasoning_enabled=overrides.get("reasoning_enabled", base.reasoning_enabled),
            tools=overrides.get("tools", base.tools),
            metadata={**base.metadata, **overrides.get("metadata", {})},
        )

        self.register_template(name, config)
        return config

    def create_agent(
        self,
        name: Optional[str] = None,
        template: Optional[str] = None,
        config: Optional[AgentConfig] = None,
    ) -> Agent:
        """
        Create a new agent.

        Args:
            name: Agent name
            template: Template name to use
            config: Custom configuration

        Returns:
            Created Agent
        """
        if config:
            final_config = config
        elif template and template in self.templates:
            final_config = self.templates[template]
            if name:
                final_config.name = name
        else:
            final_config = AgentConfig(name=name or "Assistant")

        agent = Agent(
            config=final_config,
            ai_runtime=self.ai_runtime,
            tool_registry=self.tool_registry,
            memory_manager=self.memory_manager,
        )

        self.agents[agent.id] = agent
        self._emit(ManagerEvent.AGENT_CREATED, agent.id)

        logger.info(
            "agent_created",
            agent_id=agent.id,
            name=agent.name,
            template=template,
        )

        return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        return self.agents.get(agent_id)

    def get_agent_by_name(self, name: str) -> Optional[Agent]:
        """Get an agent by name."""
        for agent in self.agents.values():
            if agent.name == name:
                return agent
        return None

    def list_agents(
        self,
        state: Optional[AgentState] = None,
        template: Optional[str] = None,
    ) -> list[Agent]:
        """List agents with optional filters."""
        agents = list(self.agents.values())

        if state:
            agents = [a for a in agents if a.state == state]

        if template and template in self.templates:
            agents = [a for a in agents if a.config.name == self.templates[template].name]

        return sorted(agents, key=lambda a: a.name)

    async def start_agent(self, agent_id: str) -> bool:
        """Start an agent."""
        agent = self.agents.get(agent_id)
        if not agent:
            return False

        await agent.start()
        self._emit(ManagerEvent.AGENT_STARTED, agent_id)
        return True

    async def stop_agent(self, agent_id: str) -> bool:
        """Stop an agent."""
        agent = self.agents.get(agent_id)
        if not agent:
            return False

        await agent.stop()
        self._emit(ManagerEvent.AGENT_STOPPED, agent_id)
        return True

    async def start_all(self) -> None:
        """Start all agents."""
        for agent_id in self.agents:
            await self.start_agent(agent_id)
        logger.info("all_agents_started", count=len(self.agents))

    async def stop_all(self) -> None:
        """Stop all agents."""
        for agent_id in self.agents:
            await self.stop_agent(agent_id)
        logger.info("all_agents_stopped", count=len(self.agents))

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent."""
        agent = self.agents.get(agent_id)
        if not agent:
            return False

        # Stop if running
        if agent.is_running:
            asyncio.create_task(self.stop_agent(agent_id))

        del self.agents[agent_id]
        logger.info("agent_deleted", agent_id=agent_id)
        return True

    def create_team(
        self,
        team_name: str,
        config: TeamConfig,
        agent_configs: list[dict[str, Any]],
    ) -> list[Agent]:
        """
        Create a team of agents.

        Args:
            team_name: Name of the team
            config: Team configuration
            agent_configs: List of agent configurations

        Returns:
            List of created agents
        """
        agents = []

        for agent_conf in agent_configs[:config.max_agents]:
            template = agent_conf.get("template")
            agent = self.create_agent(
                name=agent_conf.get("name"),
                template=template,
            )
            agents.append(agent)

        self.teams[team_name] = [a.id for a in agents]
        logger.info(
            "team_created",
            team_name=team_name,
            agent_count=len(agents),
        )

        return agents

    def get_team(self, team_name: str) -> list[Agent]:
        """Get all agents in a team."""
        agent_ids = self.teams.get(team_name, [])
        return [self.agents[aid] for aid in agent_ids if aid in self.agents]

    def add_to_team(self, team_name: str, agent_id: str) -> bool:
        """Add an agent to a team."""
        if agent_id not in self.agents:
            return False

        if team_name not in self.teams:
            self.teams[team_name] = []

        if agent_id not in self.teams[team_name]:
            self.teams[team_name].append(agent_id)

        return True

    def remove_from_team(self, team_name: str, agent_id: str) -> bool:
        """Remove an agent from a team."""
        if team_name not in self.teams:
            return False

        if agent_id in self.teams[team_name]:
            self.teams[team_name].remove(agent_id)
            return True

        return False

    def on_event(
        self,
        event: ManagerEvent,
        handler: Callable[[ManagerEventData], None],
    ) -> None:
        """Register an event handler."""
        self._handlers[event].append(handler)

    def _emit(self, event: ManagerEvent, agent_id: str, **data: Any) -> None:
        """Emit an event."""
        event_data = ManagerEventData(
            event=event,
            agent_id=agent_id,
            data=data,
        )
        asyncio.create_task(self._event_queue.put(event_data))

    async def _process_events(self) -> None:
        """Process events from the queue."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0,
                )

                for handler in self._handlers.get(event.event, []):
                    try:
                        handler(event)
                    except Exception as e:
                        logger.error(
                            "event_handler_failed",
                            event=event.event.value,
                            error=str(e),
                        )

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("event_processing_failed", error=str(e))

    async def start(self) -> None:
        """Start the manager."""
        if self._running:
            return

        self._running = True
        self._event_loop = asyncio.create_task(self._process_events())
        logger.info("agent_manager_started")

    async def stop(self) -> None:
        """Stop the manager."""
        self._running = False

        # Stop all agents
        await self.stop_all()

        if self._event_loop:
            self._event_loop.cancel()
            try:
                await self._event_loop
            except asyncio.CancelledError:
                pass

        logger.info("agent_manager_stopped")

    def get_stats(self) -> dict[str, Any]:
        """Get manager statistics."""
        states = {}
        for agent in self.agents.values():
            state = agent.state.value
            states[state] = states.get(state, 0) + 1

        return {
            "total_agents": len(self.agents),
            "agent_states": states,
            "total_teams": len(self.teams),
            "templates_available": len(self.templates),
        }
