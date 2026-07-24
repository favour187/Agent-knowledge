"""
Memory Manager

Comprehensive memory system with episodic, semantic, and procedural memory.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class MemoryType(str, Enum):
    """Types of memory."""
    EPISODIC = "episodic"       # Events and experiences
    SEMANTIC = "semantic"       # Facts and knowledge
    PROCEDURAL = "procedural"   # Skills and procedures
    WORKING = "working"         # Current context


@dataclass
class Memory:
    """
    A memory entry.

    Attributes:
        id: Unique identifier
        content: Memory content
        memory_type: Type of memory
        agent_id: Agent this memory belongs to
        importance: Importance score (0-1)
        access_count: Number of times accessed
        last_accessed_at: Last access time
        created_at: Creation time
        embedding: Vector embedding for similarity search
        metadata: Additional metadata
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    memory_type: MemoryType = MemoryType.EPISODIC
    agent_id: Optional[str] = None
    importance: float = 0.5
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    embedding: Optional[list[float]] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    source: Optional[str] = None  # Where the memory came from

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "agent_id": self.agent_id,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "tags": self.tags,
            "source": self.source,
        }

    def access(self) -> None:
        """Record an access to this memory."""
        self.access_count += 1
        self.last_accessed_at = datetime.utcnow()


class MemoryManager:
    """
    Comprehensive memory management system.

    Features:
    - Multiple memory types (episodic, semantic, procedural, working)
    - Vector embeddings for semantic search
    - Importance-based retention
    - Memory consolidation
    - Access tracking
    - Forgetting curves
    """

    def __init__(
        self,
        embedding_provider: Optional[Any] = None,
        max_memories: int = 10000,
    ):
        self.embedding_provider = embedding_provider
        self.max_memories = max_memories

        # Memory storage by type
        self._memories: dict[MemoryType, dict[str, Memory]] = {
            MemoryType.EPISODIC: {},
            MemoryType.SEMANTIC: {},
            MemoryType.PROCEDURAL: {},
            MemoryType.WORKING: {},
        }

        # Indexes for fast lookup
        self._agent_index: dict[str, set[str]] = {}  # agent_id -> memory_ids
        self._tag_index: dict[str, set[str]] = {}    # tag -> memory_ids
        self._embedding_index: list[tuple[list[float], str]] = []  # (embedding, memory_id)

        # Configuration
        self.consolidation_interval: int = 3600  # 1 hour
        self.forgetting_threshold: float = 0.1    # Importance below this is forgotten
        self.max_access_age: int = 86400 * 30     # 30 days

        self._lock = asyncio.Lock()
        self._consolidation_task: Optional[asyncio.Task] = None

        logger.info("memory_manager_initialized", max_memories=max_memories)

    async def start(self) -> None:
        """Start the memory manager."""
        self._consolidation_task = asyncio.create_task(self._consolidation_loop())

    async def stop(self) -> None:
        """Stop the memory manager."""
        if self._consolidation_task:
            self._consolidation_task.cancel()
            try:
                await self._consolidation_task
            except asyncio.CancelledError:
                pass

    async def add_memory(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        agent_id: Optional[str] = None,
        importance: float = 0.5,
        embedding: Optional[list[float]] = None,
        metadata: Optional[dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
        source: Optional[str] = None,
    ) -> Memory:
        """
        Add a new memory.

        Args:
            content: Memory content
            memory_type: Type of memory
            agent_id: Agent this memory belongs to
            importance: Importance score (0-1)
            embedding: Vector embedding
            metadata: Additional metadata
            tags: Memory tags
            source: Memory source

        Returns:
            Created Memory
        """
        async with self._lock:
            # Generate embedding if not provided
            if embedding is None and self.embedding_provider:
                embedding = await self._generate_embedding(content)

            memory = Memory(
                content=content,
                memory_type=memory_type,
                agent_id=agent_id,
                importance=importance,
                embedding=embedding,
                metadata=metadata or {},
                tags=tags or [],
                source=source,
            )

            # Store memory
            self._memories[memory_type][memory.id] = memory

            # Update indexes
            if agent_id:
                if agent_id not in self._agent_index:
                    self._agent_index[agent_id] = set()
                self._agent_index[agent_id].add(memory.id)

            for tag in memory.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(memory.id)

            if embedding:
                self._embedding_index.append((embedding, memory.id))

            # Check memory limit
            await self._enforce_memory_limit()

            logger.debug(
                "memory_added",
                memory_id=memory.id,
                memory_type=memory_type.value,
                agent_id=agent_id,
            )

            return memory

    async def search_memory(
        self,
        query: str,
        agent_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
        min_importance: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Search memories by content similarity.

        Args:
            query: Search query
            agent_id: Filter by agent
            memory_type: Filter by type
            limit: Maximum results
            min_importance: Minimum importance score

        Returns:
            List of memory results with relevance scores
        """
        if not self.embedding_provider:
            return await self._text_search(query, agent_id, memory_type, limit, min_importance)

        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return []

        results = []
        memories_to_search = self._memories

        if memory_type:
            memories_to_search = {memory_type: self._memories[memory_type]}

        for mtype, memories in memories_to_search.items():
            for memory in memories.values():
                # Filter by agent and importance
                if agent_id and memory.agent_id != agent_id:
                    continue
                if memory.importance < min_importance:
                    continue

                # Calculate similarity
                if memory.embedding:
                    similarity = self._cosine_similarity(query_embedding, memory.embedding)
                    if similarity > 0.5:
                        memory.access()
                        results.append({
                            "memory": memory.to_dict(),
                            "relevance": similarity,
                        })

        # Sort by relevance
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:limit]

    async def _text_search(
        self,
        query: str,
        agent_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
        min_importance: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Simple text-based search."""
        query_lower = query.lower()
        results = []

        memories_to_search = self._memories
        if memory_type:
            memories_to_search = {memory_type: self._memories[memory_type]}

        for mtype, memories in memories_to_search.items():
            for memory in memories.values():
                if agent_id and memory.agent_id != agent_id:
                    continue
                if memory.importance < min_importance:
                    continue

                if query_lower in memory.content.lower():
                    memory.access()
                    results.append({
                        "memory": memory.to_dict(),
                        "relevance": 1.0,
                    })

        return results[:limit]

    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Get a memory by ID."""
        for memories in self._memories.values():
            if memory_id in memories:
                memory = memories[memory_id]
                memory.access()
                return memory
        return None

    async def get_memories_by_agent(
        self,
        agent_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100,
    ) -> list[Memory]:
        """Get all memories for an agent."""
        memory_ids = self._agent_index.get(agent_id, set())
        results = []

        for memory_id in memory_ids:
            for memories in self._memories.values():
                if memory_id in memories:
                    memory = memories[memory_id]
                    if memory_type and memory.memory_type != memory_type:
                        continue
                    results.append(memory)
                    break

        results.sort(key=lambda m: m.created_at, reverse=True)
        return results[:limit]

    async def get_memories_by_tag(
        self,
        tag: str,
        limit: int = 100,
    ) -> list[Memory]:
        """Get all memories with a tag."""
        memory_ids = self._tag_index.get(tag, set())
        results = []

        for memory_id in memory_ids:
            for memories in self._memories.values():
                if memory_id in memories:
                    results.append(memories[memory_id])
                    break

        return results[:limit]

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        tags: Optional[list[str]] = None,
    ) -> bool:
        """Update a memory."""
        memory = await self.get_memory(memory_id)
        if not memory:
            return False

        if content is not None:
            memory.content = content
        if importance is not None:
            memory.importance = importance
        if tags is not None:
            memory.tags = tags

        return True

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        async with self._lock:
            for memory_type, memories in self._memories.items():
                if memory_id in memories:
                    memory = memories[memory_id]

                    # Remove from indexes
                    if memory.agent_id and memory_id in self._agent_index.get(memory.agent_id, set()):
                        self._agent_index[memory.agent_id].discard(memory_id)

                    for tag in memory.tags:
                        if memory_id in self._tag_index.get(tag, set()):
                            self._tag_index[tag].discard(memory_id)

                    del memories[memory_id]
                    logger.debug("memory_deleted", memory_id=memory_id)
                    return True

        return False

    async def consolidate_memories(self) -> int:
        """
        Consolidate memories - strengthen important ones, weaken others.

        Returns:
            Number of memories consolidated
        """
        consolidated = 0

        async with self._lock:
            for memory_type, memories in self._memories.items():
                to_delete = []

                for memory_id, memory in memories.items():
                    # Decrease importance based on access patterns
                    if memory.last_accessed_at:
                        time_since_access = (datetime.utcnow() - memory.last_accessed_at).total_seconds()
                        
                        # Apply forgetting curve
                        decay = min(1.0, time_since_access / self.max_access_age)
                        memory.importance = max(0.0, memory.importance - (decay * 0.1))

                    # Mark low importance memories for deletion
                    if memory.importance < self.forgetting_threshold:
                        to_delete.append(memory_id)

                # Delete old memories
                for memory_id in to_delete:
                    await self.delete_memory(memory_id)
                    consolidated += 1

        if consolidated > 0:
            logger.info("memories_consolidated", count=consolidated)

        return consolidated

    async def _consolidation_loop(self) -> None:
        """Background consolidation loop."""
        while True:
            try:
                await asyncio.sleep(self.consolidation_interval)
                await self.consolidate_memories()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("consolidation_failed", error=str(e))

    async def _enforce_memory_limit(self) -> None:
        """Enforce maximum memory limit."""
        total = sum(len(m) for m in self._memories.values())

        if total <= self.max_memories:
            return

        # Delete least important memories
        excess = total - self.max_memories

        # Get all memories sorted by importance
        all_memories = []
        for memories in self._memories.values():
            all_memories.extend(memories.values())

        all_memories.sort(key=lambda m: m.importance)

        for memory in all_memories[:excess]:
            await self.delete_memory(memory.id)

        logger.info("memory_limit_enforced", deleted=excess)

    async def _generate_embedding(self, text: str) -> Optional[list[float]]:
        """Generate embedding for text."""
        if self.embedding_provider:
            try:
                return await self.embedding_provider.embed(text)
            except Exception as e:
                logger.warning("embedding_generation_failed", error=str(e))
        return None

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        by_type = {
            mtype.value: len(memories)
            for mtype, memories in self._memories.items()
        }

        total = sum(by_type.values())

        return {
            "total_memories": total,
            "by_type": by_type,
            "max_memories": self.max_memories,
            "utilization": total / self.max_memories if self.max_memories > 0 else 0,
            "agents_tracked": len(self._agent_index),
            "unique_tags": len(self._tag_index),
        }

    async def clear_agent_memories(self, agent_id: str) -> int:
        """Clear all memories for an agent."""
        memory_ids = self._agent_index.get(agent_id, set()).copy()
        deleted = 0

        for memory_id in memory_ids:
            if await self.delete_memory(memory_id):
                deleted += 1

        logger.info("agent_memories_cleared", agent_id=agent_id, deleted=deleted)
        return deleted
