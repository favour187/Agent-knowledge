"""Knowledge Base - Structured knowledge storage and retrieval."""

from core.knowledge_base.manager import KnowledgeBase
from core.knowledge_base.entities import Entity, EntityRelation
from core.knowledge_base.graph import KnowledgeGraph

__all__ = [
    "KnowledgeBase",
    "Entity",
    "EntityRelation",
    "KnowledgeGraph",
]
