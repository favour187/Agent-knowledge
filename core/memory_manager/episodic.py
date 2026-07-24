"""
Episodic Memory

Stores and retrieves experiences and events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import structlog

from core.memory_manager.manager import Memory, MemoryManager, MemoryType

logger = structlog.get_logger(__name__)


@dataclass
class Episode:
    """A single episode (experience/event)."""
    agent_id: str  # Must be first: non-default field
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    events: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    emotions: list[str] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> Optional[timedelta]:
        """Get episode duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "events": self.events,
            "outcomes": self.outcomes,
            "emotions": self.emotions,
            "lessons_learned": self.lessons_learned,
            "memory_ids": self.memory_ids,
            "metadata": self.metadata,
        }


class EpisodicMemory:
    """
    Episodic memory system for storing experiences.

    Features:
    - Episode management
    - Event logging
    - Experience replay
    - Lesson extraction
    - Temporal ordering
    """

    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self._episodes: dict[str, Episode] = {}
        self._agent_episodes: dict[str, list[str]] = {}

    async def create_episode(
        self,
        agent_id: str,
        title: str = "",
        description: str = "",
    ) -> Episode:
        """Create a new episode."""
        episode = Episode(
            agent_id=agent_id,
            title=title,
            description=description,
        )

        self._episodes[episode.id] = episode

        if agent_id not in self._agent_episodes:
            self._agent_episodes[agent_id] = []
        self._agent_episodes[agent_id].append(episode.id)

        return episode

    async def add_event(
        self,
        episode_id: str,
        event_type: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add an event to an episode."""
        episode = self._episodes.get(episode_id)
        if not episode:
            return

        event = {
            "type": event_type,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        episode.events.append(event)

        # Also store as memory
        memory = await self.memory_manager.add_memory(
            content=f"{event_type}: {content}",
            memory_type=MemoryType.EPISODIC,
            agent_id=episode.agent_id,
            importance=0.6,
            source=f"episode:{episode_id}",
        )
        episode.memory_ids.append(memory.id)

    async def end_episode(
        self,
        episode_id: str,
        outcomes: Optional[list[str]] = None,
    ) -> None:
        """End an episode."""
        episode = self._episodes.get(episode_id)
        if not episode:
            return

        episode.end_time = datetime.utcnow()

        if outcomes:
            episode.outcomes.extend(outcomes)

    async def extract_lessons(
        self,
        episode_id: str,
        lessons: list[str],
    ) -> None:
        """Extract lessons from an episode."""
        episode = self._episodes.get(episode_id)
        if not episode:
            return

        episode.lessons_learned.extend(lessons)

        # Store lessons as procedural memories
        for lesson in lessons:
            await self.memory_manager.add_memory(
                content=lesson,
                memory_type=MemoryType.PROCEDURAL,
                agent_id=episode.agent_id,
                importance=0.8,
                tags=["lesson", "learned"],
                source=f"episode:{episode_id}",
            )

    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """Get an episode by ID."""
        return self._episodes.get(episode_id)

    def get_recent_episodes(
        self,
        agent_id: str,
        limit: int = 10,
    ) -> list[Episode]:
        """Get recent episodes for an agent."""
        episode_ids = self._agent_episodes.get(agent_id, [])
        episodes = [self._episodes[eid] for eid in episode_ids if eid in self._episodes]
        episodes.sort(key=lambda e: e.start_time, reverse=True)
        return episodes[:limit]

    def get_episodes_by_time_range(
        self,
        agent_id: str,
        start: datetime,
        end: datetime,
    ) -> list[Episode]:
        """Get episodes within a time range."""
        episode_ids = self._agent_episodes.get(agent_id, [])
        episodes = []

        for eid in episode_ids:
            episode = self._episodes.get(eid)
            if episode and start <= episode.start_time <= end:
                episodes.append(episode)

        episodes.sort(key=lambda e: e.start_time)
        return episodes

    async def replay_episode(self, episode_id: str) -> list[dict[str, Any]]:
        """Replay an episode as a sequence of events."""
        episode = self._episodes.get(episode_id)
        if not episode:
            return []

        replay = []
        for event in episode.events:
            replay.append({
                "event": event,
                "episode_context": {
                    "title": episode.title,
                    "description": episode.description,
                },
            })

        return replay

    def get_stats(self) -> dict[str, Any]:
        """Get episodic memory statistics."""
        return {
            "total_episodes": len(self._episodes),
            "agents_with_episodes": len(self._agent_episodes),
            "total_events": sum(len(e.events) for e in self._episodes.values()),
            "total_lessons": sum(len(e.lessons_learned) for e in self._episodes.values()),
        }
