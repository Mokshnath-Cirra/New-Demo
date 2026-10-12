"""Async SQLAlchemy 2.0 engine and session factory (SQLite or PostgreSQL)."""
from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables if they do not exist."""
    from backend import models  # noqa: F401  (registers tables on Base.metadata)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
