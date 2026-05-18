from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.infrastructure.database.models import Base
from app.infrastructure.database.session import create_async_db_engine


TABLES_IN_DELETE_ORDER = [
    "agent_plan_steps",
    "agent_plan_runs",
    "agent_scheduled_jobs",
    "agent_audit_events",
    "agent_memories",
    "chat_history",
]


@pytest.fixture()
async def mysql_engine() -> AsyncIterator[AsyncEngine]:
    settings = Settings(_env_file=None)
    engine = create_async_db_engine(settings.resolved_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table in TABLES_IN_DELETE_ORDER:
            await conn.execute(text(f"delete from {table}"))
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            for table in TABLES_IN_DELETE_ORDER:
                await conn.execute(text(f"delete from {table}"))
        await engine.dispose()
