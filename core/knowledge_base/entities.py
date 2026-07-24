"""
Knowledge Base Entities

Entity and relationship models for structured knowledge.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class EntityType(str, Enum):
    """Types of knowledge entities."""
    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    CONCEPT = "concept"
    EVENT = "event"
    OBJECT = "object"
    DOCUMENT = "document"
    TASK = "task"
    PROJECT = "project"
    CUSTOM = "custom"


@dataclass
class Entity:
    """
    A knowledge entity.

    Attributes:
        id: Unique identifier
        entity_type: Type of entity
        name: Entity name
        description: Entity description
        properties: Key-value properties
        embedding: Vector embedding for similarity
        confidence: Confidence in the entity
        source: Source of this knowledge
        created_at: Creation time
        updated_at: Last update time
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: EntityType = EntityType.CONCEPT
    name: str = ""
    description: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    embedding: Optional[list[float]] = None
    confidence: float = 1.0
    source: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "description": self.description,
            "properties": self.properties,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a property value."""
        return self.properties.get(key, default)

    def set_property(self, key: str, value: Any) -> None:
        """Set a property value."""
        self.properties[key] = value
        self.updated_at = datetime.utcnow()


@dataclass
class EntityRelation:
    """
    A relationship between entities.

    Attributes:
        id: Unique identifier
        source_id: Source entity ID
        target_id: Target entity ID
        relation_type: Type of relationship
        properties: Relationship properties
        confidence: Confidence in the relation
        bidirectional: Whether relation works both ways
        created_at: Creation time
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    relation_type: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    bidirectional: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "properties": self.properties,
            "confidence": self.confidence,
            "bidirectional": self.bidirectional,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


# Common relation types
class RelationTypes:
    """Standard relationship types."""
    IS_A = "is_a"
    HAS_A = "has_a"
    PART_OF = "part_of"
    LOCATED_IN = "located_in"
    WORKS_AT = "works_at"
    CREATED_BY = "created_by"
    RELATED_TO = "related_to"
    DEPENDS_ON = "depends_on"
    REFERENCES = "references"
    CAUSES = "causes"
    BEFORE = "before"
    AFTER = "after"
