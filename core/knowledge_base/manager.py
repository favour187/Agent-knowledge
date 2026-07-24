"""
Knowledge Base Manager

Manages entities, relationships, and knowledge operations.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import structlog

from core.knowledge_base.entities import (
    Entity,
    EntityRelation,
    EntityType,
    RelationTypes,
)
from core.knowledge_base.graph import KnowledgeGraph

logger = structlog.get_logger(__name__)


class KnowledgeBase:
    """
    Structured knowledge storage and retrieval system.

    Features:
    - Entity management
    - Relationship management
    - Knowledge graph operations
    - Semantic search
    - Inference
    - Version control for facts
    """

    def __init__(self, embedding_provider: Optional[Any] = None):
        self.embedding_provider = embedding_provider

        # Storage
        self._entities: dict[str, Entity] = {}
        self._relations: dict[str, EntityRelation] = {}
        self._name_index: dict[str, str] = {}  # name -> entity_id

        # Graph for traversal
        self._graph = KnowledgeGraph()

        # Statistics
        self._stats = {
            "entities_created": 0,
            "relations_created": 0,
            "queries_executed": 0,
        }

        logger.info("knowledge_base_initialized")

    async def add_entity(
        self,
        name: str,
        entity_type: EntityType,
        description: str = "",
        properties: Optional[dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> Entity:
        """
        Add a new entity.

        Args:
            name: Entity name
            entity_type: Type of entity
            description: Entity description
            properties: Key-value properties
            source: Source of this knowledge

        Returns:
            Created Entity
        """
        # Check for existing entity with same name
        name_lower = name.lower()
        if name_lower in self._name_index:
            existing = self._entities[self._name_index[name_lower]]
            logger.debug("entity_exists", entity_id=existing.id, name=name)
            return existing

        # Generate embedding
        embedding = None
        if self.embedding_provider:
            try:
                text = f"{name}: {description}"
                embedding = await self.embedding_provider.embed(text)
            except Exception as e:
                logger.warning("embedding_failed", error=str(e))

        # Create entity
        entity = Entity(
            entity_type=entity_type,
            name=name,
            description=description,
            properties=properties or {},
            embedding=embedding,
            source=source,
        )

        self._entities[entity.id] = entity
        self._name_index[name_lower] = entity.id
        self._stats["entities_created"] += 1

        # Add to graph
        self._graph.add_node(entity.id, entity_type.value)

        logger.debug("entity_added", entity_id=entity.id, name=name)
        return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        return self._entities.get(entity_id)

    def get_entity_by_name(self, name: str) -> Optional[Entity]:
        """Get an entity by name."""
        entity_id = self._name_index.get(name.lower())
        return self._entities.get(entity_id) if entity_id else None

    async def update_entity(
        self,
        entity_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        properties: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Update an entity."""
        entity = self._entities.get(entity_id)
        if not entity:
            return False

        if name:
            # Update name index
            old_name_lower = entity.name.lower()
            del self._name_index[old_name_lower]
            entity.name = name
            self._name_index[name.lower()] = entity_id

        if description:
            entity.description = description

        if properties:
            entity.properties.update(properties)

        entity.updated_at = entity.updated_at
        return True

    async def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and its relations."""
        entity = self._entities.get(entity_id)
        if not entity:
            return False

        # Remove from name index
        del self._name_index[entity.name.lower()]

        # Remove relations
        relations_to_delete = [
            rid for rid, rel in self._relations.items()
            if rel.source_id == entity_id or rel.target_id == entity_id
        ]
        for rid in relations_to_delete:
            del self._relations[rid]

        # Remove from graph
        self._graph.remove_node(entity_id)

        # Remove entity
        del self._entities[entity_id]

        logger.debug("entity_deleted", entity_id=entity_id)
        return True

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: Optional[dict[str, Any]] = None,
        bidirectional: bool = False,
    ) -> Optional[EntityRelation]:
        """Add a relationship between entities."""
        # Verify entities exist
        if source_id not in self._entities or target_id not in self._entities:
            return None

        # Check for existing relation
        for rel in self._relations.values():
            if (rel.source_id == source_id and rel.target_id == target_id
                    and rel.relation_type == relation_type):
                return rel

        relation = EntityRelation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            properties=properties or {},
            bidirectional=bidirectional,
        )

        self._relations[relation.id] = relation
        self._stats["relations_created"] += 1

        # Add to graph
        self._graph.add_edge(source_id, target_id, relation_type)
        if bidirectional:
            self._graph.add_edge(target_id, source_id, relation_type)

        logger.debug(
            "relation_added",
            relation_id=relation.id,
            source=source_id,
            target=target_id,
            type=relation_type,
        )

        return relation

    def get_relations(
        self,
        entity_id: Optional[str] = None,
        relation_type: Optional[str] = None,
    ) -> list[EntityRelation]:
        """Get relations, optionally filtered."""
        relations = list(self._relations.values())

        if entity_id:
            relations = [
                r for r in relations
                if r.source_id == entity_id or r.target_id == entity_id
            ]

        if relation_type:
            relations = [r for r in relations if r.relation_type == relation_type]

        return relations

    def get_neighbors(
        self,
        entity_id: str,
        relation_type: Optional[str] = None,
        depth: int = 1,
    ) -> list[tuple[Entity, str]]:
        """
        Get neighboring entities.

        Args:
            entity_id: Starting entity
            relation_type: Filter by relation type
            depth: Traversal depth

        Returns:
            List of (entity, relation_type) tuples
        """
        neighbors = []
        visited = {entity_id}

        def traverse(current_id: str, current_depth: int):
            if current_depth > depth:
                return

            for relation in self._relations.values():
                if relation.source_id != current_id:
                    continue
                if relation_type and relation.relation_type != relation_type:
                    continue

                if relation.target_id not in visited:
                    visited.add(relation.target_id)
                    entity = self._entities.get(relation.target_id)
                    if entity:
                        neighbors.append((entity, relation.relation_type))
                        traverse(relation.target_id, current_depth + 1)

        traverse(entity_id, 0)
        return neighbors

    async def search(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 10,
    ) -> list[Entity]:
        """
        Search for entities.

        Args:
            query: Search query
            entity_type: Filter by entity type
            limit: Maximum results

        Returns:
            List of matching entities
        """
        self._stats["queries_executed"] += 1

        results = []

        # Simple text search
        query_lower = query.lower()
        for entity in self._entities.values():
            # Type filter
            if entity_type and entity.entity_type != entity_type:
                continue

            # Text match
            score = 0
            if query_lower in entity.name.lower():
                score = 2
            elif query_lower in entity.description.lower():
                score = 1

            if score > 0:
                results.append((entity, score))

        # Sort by score
        results.sort(key=lambda x: x[1], reverse=True)

        return [e for e, _ in results[:limit]]

    async def infer(
        self,
        entity_id: str,
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """
        Infer knowledge from existing facts.

        Args:
            entity_id: Starting entity
            max_hops: Maximum inference depth

        Returns:
            List of inferred facts
        """
        inferred = []
        visited = {entity_id}

        def infer_recursive(current_id: str, path: list[str], depth: int):
            if depth > max_hops:
                return

            entity = self._entities.get(current_id)
            if not entity:
                return

            for relation in self._relations.values():
                if relation.source_id != current_id:
                    continue

                next_id = relation.target_id
                if next_id in visited:
                    continue

                visited.add(next_id)
                next_entity = self._entities.get(next_id)

                if next_entity:
                    # Record inference
                    inferred.append({
                        "from": entity.to_dict(),
                        "relation": relation.relation_type,
                        "to": next_entity.to_dict(),
                        "path": path + [relation.relation_type],
                    })

                    infer_recursive(next_id, path + [relation.relation_type], depth + 1)

        infer_recursive(entity_id, [], 0)
        return inferred

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        by_type = {}
        for entity in self._entities.values():
            etype = entity.entity_type.value
            by_type[etype] = by_type.get(etype, 0) + 1

        return {
            "total_entities": len(self._entities),
            "total_relations": len(self._relations),
            "by_entity_type": by_type,
            **self._stats,
        }

    def export_graph(self) -> dict[str, Any]:
        """Export the knowledge graph as JSON."""
        entities = [e.to_dict() for e in self._entities.values()]
        relations = [r.to_dict() for r in self._relations.values()]

        return {
            "entities": entities,
            "relations": relations,
        }
