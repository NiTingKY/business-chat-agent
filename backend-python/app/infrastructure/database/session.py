"""Async SQLAlchemy engine and session factory for MySQL."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_async_db_engine(database_url: str, **kwargs: Any) -> AsyncEngine:
    if not database_url.startswith("mysql+aiomysql"):
        if database_url.startswith("mysql://"):
            database_url = database_url.replace("mysql://", "mysql+aiomysql://", 1)
    if database_url.startswith("sqlite"):
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
    return create_async_engine(database_url, pool_pre_ping=True, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
