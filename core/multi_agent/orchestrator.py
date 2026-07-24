"""
Multi-Agent Orchestrator

Coordinates multiple agents working together on complex tasks.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from core.agent_manager.agent import Agent

logger = structlog.get_logger(__name__)


class TeamRole(str, Enum):
    """Roles for team members."""
    COORDINATOR = "coordinator"   # Orchestrates the team
    EXPERT = "expert"           # Subject matter expert
    REVIEWER = "reviewer"       # Reviews and critiques
    EXECUTOR = "executor"       # Executes tasks
    SYNTHESIZER = "synthesizer"  # Combines results


class CollaborationMode(str, Enum):
    """How agents collaborate."""
    SEQUENTIAL = "sequential"   # One at a time
    PARALLEL = "parallel"       # Simultaneous execution
    HIERARCHICAL = "hierarchical"  # Chain of command
    CONSENSUS = "consensus"     # Vote on decisions


@dataclass
class TeamMember:
    """A member of a team."""
    agent: Agent
    role: TeamRole
    capabilities: list[str] = field(default_factory=list)
    current_task: Optional[str] = None
    performance_score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent.id,
            "name": self.agent.name,
            "role": self.role.value,
            "capabilities": self.capabilities,
            "current_task": self.current_task,
            "performance_score": self.performance_score,
        }


@dataclass
class Team:
    """A team of agents working together."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    members: list[TeamMember] = field(default_factory=list)
    collaboration_mode: CollaborationMode = CollaborationMode.SEQUENTIAL
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_member(self, agent_id: str) -> Optional[TeamMember]:
        """Get a team member by agent ID."""
        for member in self.members:
            if member.agent.id == agent_id:
                return member
        return None

    def get_by_role(self, role: TeamRole) -> list[TeamMember]:
        """Get all members with a specific role."""
        return [m for m in self.members if m.role == role]

    def get_coordinator(self) -> Optional[TeamMember]:
        """Get the team coordinator."""
        coordinators = self.get_by_role(TeamRole.COORDINATOR)
        return coordinators[0] if coordinators else None


class MultiAgentOrchestrator:
    """
    Orchestrates multiple agents working together.

    Features:
    - Team creation and management
    - Task delegation
    - Result aggregation
    - Conflict resolution
    - Performance tracking
    """

    def __init__(self):
        self.teams: dict[str, Team] = {}
        self._event_handlers: dict[str, list[Callable]] = {}

        logger.info("multi_agent_orchestrator_initialized")

    def create_team(
        self,
        name: str,
        description: str = "",
        mode: CollaborationMode = CollaborationMode.SEQUENTIAL,
    ) -> Team:
        """
        Create a new team.

        Args:
            name: Team name
            description: Team description
            mode: Collaboration mode

        Returns:
            Created Team
        """
        team = Team(
            name=name,
            description=description,
            collaboration_mode=mode,
        )
        self.teams[team.id] = team

        logger.info("team_created", team_id=team.id, name=name)
        return team

    def add_member(
        self,
        team_id: str,
        agent: Agent,
        role: TeamRole = TeamRole.EXPERT,
        capabilities: Optional[list[str]] = None,
    ) -> bool:
        """Add a member to a team."""
        team = self.teams.get(team_id)
        if not team:
            return False

        # Check if already a member
        if team.get_member(agent.id):
            return False

        member = TeamMember(
            agent=agent,
            role=role,
            capabilities=capabilities or [],
        )
        team.members.append(member)

        logger.debug(
            "member_added",
            team_id=team_id,
            agent_id=agent.id,
            role=role.value,
        )
        return True

    def remove_member(self, team_id: str, agent_id: str) -> bool:
        """Remove a member from a team."""
        team = self.teams.get(team_id)
        if not team:
            return False

        member = team.get_member(agent_id)
        if not member:
            return False

        team.members.remove(member)
        logger.debug("member_removed", team_id=team_id, agent_id=agent_id)
        return True

    async def delegate_task(
        self,
        team_id: str,
        task: str,
        role: Optional[TeamRole] = None,
        specific_agent_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Delegate a task to a team member.

        Args:
            team_id: Team ID
            task: Task description
            role: Preferred role (auto-selects if not specified)
            specific_agent_id: Specific agent to delegate to

        Returns:
            Task result
        """
        team = self.teams.get(team_id)
        if not team:
            return {"success": False, "error": "Team not found"}

        # Select agent
        if specific_agent_id:
            member = team.get_member(specific_agent_id)
        elif role:
            members = team.get_by_role(role)
            member = members[0] if members else None
        else:
            # Auto-select based on availability
            available = [m for m in team.members if not m.current_task]
            member = available[0] if available else None

        if not member:
            return {"success": False, "error": "No available agent"}

        # Assign task
        member.current_task = task

        try:
            # Execute task
            result = await member.agent.act(task)

            # Clear task
            member.current_task = None

            return {
                "success": True,
                "agent_id": member.agent.id,
                "result": result,
            }

        except Exception as e:
            member.current_task = None
            return {
                "success": False,
                "agent_id": member.agent.id,
                "error": str(e),
            }

    async def run_parallel_tasks(
        self,
        team_id: str,
        tasks: list[str],
    ) -> list[dict[str, Any]]:
        """
        Run multiple tasks in parallel across team members.

        Args:
            team_id: Team ID
            tasks: List of task descriptions

        Returns:
            List of results
        """
        team = self.teams.get(team_id)
        if not team:
            return [{"success": False, "error": "Team not found"}] * len(tasks)

        # Assign tasks to available members
        assignments = []
        for i, task in enumerate(tasks):
            member_index = i % len(team.members)
            member = team.members[member_index]
            assignments.append((member, task))

        # Execute in parallel
        async def execute_task(member: TeamMember, task: str) -> dict[str, Any]:
            member.current_task = task
            try:
                result = await member.agent.act(task)
                return {
                    "success": True,
                    "agent_id": member.agent.id,
                    "task": task,
                    "result": result,
                }
            except Exception as e:
                return {
                    "success": False,
                    "agent_id": member.agent.id,
                    "task": task,
                    "error": str(e),
                }
            finally:
                member.current_task = None

        # Run all tasks concurrently
        results = await asyncio.gather(
            *[execute_task(m, t) for m, t in assignments],
            return_exceptions=True,
        )

        return [r if isinstance(r, dict) else {"success": False, "error": str(r)} for r in results]

    async def aggregate_results(
        self,
        team_id: str,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Aggregate results from multiple agents.

        Args:
            team_id: Team ID
            results: List of results to aggregate

        Returns:
            Aggregated result
        """
        team = self.teams.get(team_id)
        if not team:
            return {"success": False, "error": "Team not found"}

        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        return {
            "success": len(successful) > 0,
            "total_tasks": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "results": results,
            "summary": f"{len(successful)}/{len(results)} tasks completed successfully",
        }

    def get_team(self, team_id: str) -> Optional[Team]:
        """Get a team by ID."""
        return self.teams.get(team_id)

    def list_teams(self) -> list[Team]:
        """List all teams."""
        return list(self.teams.values())

    def delete_team(self, team_id: str) -> bool:
        """Delete a team."""
        if team_id in self.teams:
            del self.teams[team_id]
            logger.info("team_deleted", team_id=team_id)
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get orchestrator statistics."""
        total_members = sum(len(t.members) for t in self.teams.values())
        active_tasks = sum(
            1 for t in self.teams.values()
            for m in t.members if m.current_task
        )

        return {
            "total_teams": len(self.teams),
            "total_members": total_members,
            "active_tasks": active_tasks,
            "teams_by_mode": {
                mode.value: sum(1 for t in self.teams.values() if t.collaboration_mode == mode)
                for mode in CollaborationMode
            },
        }
