from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent_runtime.events import AgentEvent
from app.infrastructure.database.repository import AgentAuditRepository
from app.infrastructure.database.session import create_session_factory


class PersistentAuditStore:
    """Persists AgentRuntime events for audit and debugging."""

    def __init__(self, db_engine: AsyncEngine | None) -> None:
        self._db_engine = db_engine

    async def save_events(self, events: list[AgentEvent]) -> None:
        if not self._db_engine or not events:
            return
        try:
            factory = create_session_factory(self._db_engine)
            async with factory() as session:
                repo = AgentAuditRepository(session)
                for event in events:
                    payload = dict(event.payload)
                    await repo.save_event(
                        event_id=event.event_id,
                        turn_id=event.turn_id,
                        agent_id=str(payload.get("agent_id") or ""),
                        session_id=payload.get("session_id"),
                        user_id=payload.get("user_id"),
                        event_type=event.type,
                        payload={**payload, "timestamp": event.timestamp},
                    )
        except Exception:
            return

    async def list_events(
        self,
        *,
        turn_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self._db_engine:
            return []
        try:
            factory = create_session_factory(self._db_engine)
            async with factory() as session:
                repo = AgentAuditRepository(session)
                rows = await repo.list_events(
                    turn_id=turn_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    limit=limit,
                )
        except Exception:
            return []
        return [
            {
                "id": row.id,
                "event_id": row.event_id,
                "turn_id": row.turn_id,
                "agent_id": row.agent_id,
                "session_id": row.session_id,
                "user_id": row.user_id,
                "event_type": row.event_type,
                "payload": row.payload or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
