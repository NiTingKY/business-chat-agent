from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent_runtime.audit import PersistentAuditStore
from app.infrastructure.database.models import Base
from app.infrastructure.database.session import create_async_db_engine
from app.main import create_app


@pytest.mark.asyncio
async def test_persistent_audit_store_saves_and_filters_events(tmp_path: Path) -> None:
    from app.agent_runtime.events import AgentEvent

    engine = create_async_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    store = PersistentAuditStore(engine)
    turn_id = str(uuid.uuid4())
    await store.save_events(
        [
            AgentEvent(
                type="turn.started",
                turn_id=turn_id,
                timestamp=time.time(),
                payload={"agent_id": "travel-agent", "session_id": "s1", "user_id": "u1"},
            ),
            AgentEvent(
                type="model.call",
                turn_id=turn_id,
                timestamp=time.time(),
                payload={"agent_id": "travel-agent", "session_id": "s1", "user_id": "u1"},
            ),
        ]
    )

    events = await store.list_events(session_id="s1")
    assert {event["event_type"] for event in events} == {"turn.started", "model.call"}
    assert all(event["turn_id"] == turn_id for event in events)
    await engine.dispose()


def test_audit_api_returns_events_after_chat_turn() -> None:
    app = create_app()
    session_id = f"audit-api-{uuid.uuid4()}"
    with TestClient(app) as client:
        chat = client.post(
            "/api/v1/chat",
            json={
                "session_id": session_id,
                "user_id": "audit-user",
                "messages": [{"role": "user", "content": "我的职级是经理，我喜欢高铁优先。"}],
            },
        )
        assert chat.status_code == 200

        audit = client.get("/api/v1/audit/events", params={"session_id": session_id})
        assert audit.status_code == 200
        events = audit.json()["events"]
        event_types = {event["event_type"] for event in events}
        assert "turn.started" in event_types
        assert "memory.loaded" in event_types
        assert "model.call" in event_types
        assert "agent.completed" in event_types
