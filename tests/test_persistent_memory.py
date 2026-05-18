from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.agent.orchestrator import TravelOrchestrator
from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.session import AgentSessionManager
from app.agent_runtime.turn import AgentTurnContext
from app.core.memory.persistent_store import PersistentAgentMemoryStore
from app.domain.schemas import ChatMessage, MessageRole
from app.infrastructure.database.models import Base
from app.infrastructure.database.session import create_async_db_engine
from app.tools.registry import AgentToolRegistry


class NoopLLM:
    model = "noop"


@pytest.mark.asyncio
async def test_semantic_memory_persists_across_runtime_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    engine = create_async_db_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_id = f"persistent-{uuid4()}"
    user_id = "u1"

    first_orchestrator = TravelOrchestrator(
        llm=NoopLLM(),  # type: ignore[arg-type]
        tool_registry=AgentToolRegistry(),
        system_prompt="test",
    )
    first_runtime = AgentRuntime(
        agent_id="travel-agent",
        orchestrator=first_orchestrator,
        sessions=AgentSessionManager(engine),
        memory_store=PersistentAgentMemoryStore(engine),
    )
    await first_runtime._build_turn_messages(
        AgentTurnContext(
            agent_id="travel-agent",
            session_id=session_id,
            user_id=user_id,
            messages=[ChatMessage(role=MessageRole.USER, content="我的职级是经理，我喜欢高铁优先。")],
        )
    )
    first_orchestrator._record_memory(
        session_id,
        [ChatMessage(role=MessageRole.USER, content="我的职级是经理，我喜欢高铁优先。")],
        {
            "choices": [
                {"message": {"content": "已记录。"}},
            ]
        },
    )
    await first_runtime._persist_semantic_memory(
        AgentTurnContext(
            agent_id="travel-agent",
            session_id=session_id,
            user_id=user_id,
            messages=[],
        )
    )

    second_orchestrator = TravelOrchestrator(
        llm=NoopLLM(),  # type: ignore[arg-type]
        tool_registry=AgentToolRegistry(),
        system_prompt="test",
    )
    second_runtime = AgentRuntime(
        agent_id="travel-agent",
        orchestrator=second_orchestrator,
        sessions=AgentSessionManager(engine),
        memory_store=PersistentAgentMemoryStore(engine),
    )
    messages = await second_runtime._build_turn_messages(
        AgentTurnContext(
            agent_id="travel-agent",
            session_id=session_id,
            user_id=user_id,
            messages=[ChatMessage(role=MessageRole.USER, content="下次去上海怎么安排？")],
        )
    )
    context = second_orchestrator._memory.build_context(
        messages,
        session_id=session_id,
        user_id=user_id,
    )

    assert context.messages[0].role is MessageRole.SYSTEM
    assert "我的职级是经理" in context.messages[0].content
    assert "高铁优先" in context.messages[0].content

    await engine.dispose()
