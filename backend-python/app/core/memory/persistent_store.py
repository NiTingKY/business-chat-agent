from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.memory.agent_memory import SemanticMemory
from app.infrastructure.database.repository import AgentMemoryRepository
from app.infrastructure.database.session import create_session_factory


class PersistentAgentMemoryStore:
    """SQLite/SQLAlchemy-backed semantic memory store."""

    def __init__(self, db_engine: AsyncEngine | None) -> None:
        self._db_engine = db_engine

    async def load(
        self,
        *,
        agent_id: str,
        session_id: str | None,
        user_id: str | None,
    ) -> list[SemanticMemory]:
        if not self._db_engine or not session_id:
            return []
        try:
            factory = create_session_factory(self._db_engine)
            async with factory() as session:
                repo = AgentMemoryRepository(session)
                rows = await repo.list_memories(
                    agent_id=agent_id,
                    session_id=session_id,
                    user_id=user_id,
                )
        except Exception:
            return []
        return [
            SemanticMemory(
                text=row.text,
                source=row.source,
                importance=float(row.importance or 0.6),
            )
            for row in rows
        ]

    async def save(
        self,
        *,
        agent_id: str,
        session_id: str | None,
        user_id: str | None,
        memories: list[SemanticMemory],
    ) -> None:
        if not self._db_engine or not session_id or not memories:
            return
        try:
            factory = create_session_factory(self._db_engine)
            async with factory() as session:
                repo = AgentMemoryRepository(session)
                for memory in memories:
                    await repo.save_memory(
                        agent_id=agent_id,
                        session_id=session_id,
                        user_id=user_id,
                        text=memory.text,
                        source=memory.source,
                        importance=memory.importance,
                    )
        except Exception:
            return
