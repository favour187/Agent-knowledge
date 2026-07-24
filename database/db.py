"""
Database engine and session management.

Defaults to a local SQLite file (zero config, good for dev/tests) via
aiosqlite. Set DATABASE_URL to a real Postgres DSN in production, e.g.:

    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/arena

NOTE: database/migrations/001_initial_schema.sql is written for real
Postgres + pgvector (VECTOR columns, ivfflat indexes, uuid-ossp). The
SQLAlchemy models in database/models.py describe the same tables in a
database-agnostic way so this also works against SQLite for local
development/testing. For a real Postgres deployment, run the SQL migration
directly (psql -f database/migrations/001_initial_schema.sql) to get the
real pgvector columns and indexes; init_db()/create_all() here is meant for
local dev/testing convenience, not a substitute for that migration.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def _default_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        # Normalize plain "postgresql://" to the asyncpg driver SQLAlchemy needs
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    # Zero-config local fallback
    return "sqlite+aiosqlite:///./arena.db"


DATABASE_URL = _default_database_url()

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create tables if they don't exist yet (dev/test convenience).

    In production against Postgres, prefer running the real SQL migration
    (database/migrations/001_initial_schema.sql) so you get pgvector columns
    and ivfflat indexes; this only creates plain-equivalent tables.
    """
    import database.models  # noqa: F401  (ensure models are registered on Base)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request."""
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for a DB session outside of FastAPI's DI (e.g. scripts)."""
    async with SessionLocal() as session:
        yield session
