"""
Semantic Memory

Stores facts, concepts, and general knowledge.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from core.memory_manager.manager import Memory, MemoryManager, MemoryType

logger = structlog.get_logger(__name__)


class ConceptType(str, Enum):
    """Types of semantic concepts."""
    ENTITY = "entity"
    RELATION = "relation"
    RULE = "rule"
    CATEGORY = "category"
    PROPERTY = "property"


@dataclass
class Fact:
    """A factual statement."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subject: str = ""
    predicate: str = ""
    object: str = ""
    confidence: float = 1.0
    source: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    verified_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_triple(self) -> tuple[str, str, str]:
        """Get as (subject, predicate, object) triple."""
        return (self.subject, self.predicate, self.object)

    def to_natural_language(self) -> str:
        """Convert to natural language."""
        return f"{self.subject} {self.predicate} {self.object}."

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "metadata": self.metadata,
        }


@dataclass
class Concept:
    """A semantic concept."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    concept_type: ConceptType = ConceptType.ENTITY
    description: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    related_concepts: list[str] = field(default_factory=list)  # Concept IDs
    examples: list[str] = field(default_factory=list)
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "concept_type": self.concept_type.value,
            "description": self.description,
            "properties": self.properties,
            "related_concepts": self.related_concepts,
            "examples": self.examples,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class SemanticMemory:
    """
    Semantic memory for storing facts and concepts.

    Features:
    - Fact storage and retrieval
    - Concept management
    - Knowledge graph operations
    - Inference capabilities
    - Confidence tracking
    """

    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self._facts: dict[str, Fact] = {}
        self._concepts: dict[str, Concept] = {}
        self._subject_index: dict[str, set[str]] = {}  # subject -> fact_ids
        self._predicate_index: dict[str, set[str]] = {}  # predicate -> fact_ids
        self._concept_names: dict[str, str] = {}  # name -> concept_id

    async def add_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 1.0,
        source: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Fact:
        """Add a factual statement."""
        fact = Fact(
            subject=subject,
            predicate=predicate,
            object=object,
            confidence=confidence,
            source=source,
            metadata=metadata or {},
        )

        self._facts[fact.id] = fact

        # Update indexes
        if subject not in self._subject_index:
            self._subject_index[subject] = set()
        self._subject_index[subject].add(fact.id)

        if predicate not in self._predicate_index:
            self._predicate_index[predicate] = set()
        self._predicate_index[predicate].add(fact.id)

        # Store as semantic memory
        await self.memory_manager.add_memory(
            content=fact.to_natural_language(),
            memory_type=MemoryType.SEMANTIC,
            importance=confidence * 0.7,
            tags=[subject.lower(), predicate.lower(), "fact"],
            source=f"fact:{fact.id}",
        )

        return fact

    async def add_concept(
        self,
        name: str,
        concept_type: ConceptType = ConceptType.ENTITY,
        description: str = "",
        properties: Optional[dict[str, Any]] = None,
        examples: Optional[list[str]] = None,
    ) -> Concept:
        """Add a concept."""
        # Check if concept already exists
        if name.lower() in self._concept_names:
            return self._concepts[self._concept_names[name.lower()]]

        concept = Concept(
            name=name,
            concept_type=concept_type,
            description=description,
            properties=properties or {},
            examples=examples or [],
        )

        self._concepts[concept.id] = concept
        self._concept_names[name.lower()] = concept.id

        # Store as semantic memory
        await self.memory_manager.add_memory(
            content=f"{name}: {description}",
            memory_type=MemoryType.SEMANTIC,
            importance=0.7,
            tags=[concept_type.value, "concept", name.lower()],
            source=f"concept:{concept.id}",
        )

        return concept

    def relate_concepts(
        self,
        concept_id1: str,
        concept_id2: str,
        relation_type: str,
    ) -> bool:
        """Create a relationship between concepts."""
        concept1 = self._concepts.get(concept_id1)
        concept2 = self._concepts.get(concept_id2)

        if not concept1 or not concept2:
            return False

        if concept_id2 not in concept1.related_concepts:
            concept1.related_concepts.append(concept_id2)
        if concept_id1 not in concept2.related_concepts:
            concept2.related_concepts.append(concept_id1)

        # Also store as a fact
        asyncio.create_task(self.add_fact(
            subject=concept1.name,
            predicate=relation_type,
            object=concept2.name,
            confidence=0.9,
        ))

        return True

    def get_facts_about(self, subject: str) -> list[Fact]:
        """Get all facts about a subject."""
        fact_ids = self._subject_index.get(subject, set())
        return [self._facts[fid] for fid in fact_ids if fid in self._facts]

    def get_facts_by_predicate(self, predicate: str) -> list[Fact]:
        """Get all facts with a specific predicate."""
        fact_ids = self._predicate_index.get(predicate, set())
        return [self._facts[fid] for fid in fact_ids if fid in self._facts]

    def get_concept(self, concept_id: str) -> Optional[Concept]:
        """Get a concept by ID."""
        return self._concepts.get(concept_id)

    def get_concept_by_name(self, name: str) -> Optional[Concept]:
        """Get a concept by name."""
        concept_id = self._concept_names.get(name.lower())
        return self._concepts.get(concept_id) if concept_id else None

    def get_related_concepts(self, concept_id: str) -> list[Concept]:
        """Get concepts related to another concept."""
        concept = self._concepts.get(concept_id)
        if not concept:
            return []

        return [
            self._concepts[cid]
            for cid in concept.related_concepts
            if cid in self._concepts
        ]

    async def query(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
    ) -> list[Fact]:
        """Query facts matching criteria."""
        results = list(self._facts.values())

        if subject:
            results = [f for f in results if f.subject == subject]
        if predicate:
            results = [f for f in results if f.predicate == predicate]
        if object:
            results = [f for f in results if f.object == object]

        return results

    def verify_fact(self, fact_id: str) -> bool:
        """Mark a fact as verified."""
        fact = self._facts.get(fact_id)
        if not fact:
            return False

        fact.verified_at = datetime.utcnow()
        fact.confidence = min(1.0, fact.confidence + 0.1)
        return True

    def get_stats(self) -> dict[str, Any]:
        """Get semantic memory statistics."""
        return {
            "total_facts": len(self._facts),
            "total_concepts": len(self._concepts),
            "subjects": len(self._subject_index),
            "predicates": len(self._predicate_index),
            "verified_facts": sum(1 for f in self._facts.values() if f.verified_at),
            "avg_confidence": (
                sum(f.confidence for f in self._facts.values()) / len(self._facts)
                if self._facts else 0
            ),
        }
