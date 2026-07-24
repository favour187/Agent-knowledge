"""Knowledge Routes - Knowledge base endpoints, backed by the real
`knowledge_entities` / `knowledge_relations` tables."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_db
from database.models import KnowledgeEntity, KnowledgeRelation

router = APIRouter()


class EntityCreate(BaseModel):
    """Entity creation request."""
    name: str
    entity_type: str = "concept"
    description: str = ""
    properties: dict = {}


class EntityResponse(BaseModel):
    """Entity response."""
    id: str
    name: str
    entity_type: str
    description: str
    properties: dict
    created_at: str


class RelationCreate(BaseModel):
    """Relation creation request."""
    source_id: str
    target_id: str
    relation_type: str
    properties: dict = {}


class RelationResponse(BaseModel):
    """Relation response."""
    id: str
    source_id: str
    target_id: str
    relation_type: str
    created_at: str


def _entity_to_response(entity: KnowledgeEntity) -> EntityResponse:
    return EntityResponse(
        id=entity.id,
        name=entity.name,
        entity_type=entity.entity_type,
        description=entity.description,
        properties=entity.properties,
        created_at=entity.created_at.isoformat(),
    )


@router.get("/entity", response_model=list[EntityResponse])
async def search_entities(
    query: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[EntityResponse]:
    """Search knowledge entities."""
    stmt = select(KnowledgeEntity)
    if query:
        stmt = stmt.where(KnowledgeEntity.name.ilike(f"%{query}%"))
    if entity_type:
        stmt = stmt.where(KnowledgeEntity.entity_type == entity_type)
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    return [_entity_to_response(e) for e in result.scalars().all()]


@router.post("/entity", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(entity: EntityCreate, db: AsyncSession = Depends(get_db)) -> EntityResponse:
    """Create a new entity."""
    db_entity = KnowledgeEntity(
        name=entity.name,
        entity_type=entity.entity_type,
        description=entity.description,
        properties=entity.properties,
    )
    db.add(db_entity)
    await db.commit()
    await db.refresh(db_entity)
    return _entity_to_response(db_entity)


@router.get("/entity/{entity_id}", response_model=EntityResponse)
async def get_entity(entity_id: str, db: AsyncSession = Depends(get_db)) -> EntityResponse:
    """Get entity by ID."""
    result = await db.execute(select(KnowledgeEntity).where(KnowledgeEntity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return _entity_to_response(entity)


@router.put("/entity/{entity_id}", response_model=EntityResponse)
async def update_entity(entity_id: str, entity: EntityCreate, db: AsyncSession = Depends(get_db)) -> EntityResponse:
    """Update an entity."""
    result = await db.execute(select(KnowledgeEntity).where(KnowledgeEntity.id == entity_id))
    db_entity = result.scalar_one_or_none()
    if not db_entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    db_entity.name = entity.name
    db_entity.entity_type = entity.entity_type
    db_entity.description = entity.description
    db_entity.properties = entity.properties
    await db.commit()
    await db.refresh(db_entity)
    return _entity_to_response(db_entity)


@router.delete("/entity/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(entity_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete an entity."""
    result = await db.execute(select(KnowledgeEntity).where(KnowledgeEntity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    await db.delete(entity)
    await db.commit()


@router.post("/relation", response_model=RelationResponse, status_code=status.HTTP_201_CREATED)
async def create_relation(relation: RelationCreate, db: AsyncSession = Depends(get_db)) -> RelationResponse:
    """Create a new relation between two existing entities."""
    for entity_id in (relation.source_id, relation.target_id):
        result = await db.execute(select(KnowledgeEntity).where(KnowledgeEntity.id == entity_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity not found: {entity_id}")

    db_relation = KnowledgeRelation(
        source_id=relation.source_id,
        target_id=relation.target_id,
        relation_type=relation.relation_type,
        properties=relation.properties,
    )
    db.add(db_relation)
    await db.commit()
    await db.refresh(db_relation)

    return RelationResponse(
        id=db_relation.id,
        source_id=db_relation.source_id,
        target_id=db_relation.target_id,
        relation_type=db_relation.relation_type,
        created_at=db_relation.created_at.isoformat(),
    )
