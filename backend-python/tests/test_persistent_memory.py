from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.orchestrator import TravelOrchestrator
from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.session import AgentSessionManager
from app.agent_runtime.turn import AgentTurnContext
from app.core.memory.persistent_store import PersistentAgentMemoryStore
from app.core.memory.agent_memory import SemanticMemory
from app.domain.schemas import ChatMessage, MessageRole
from app.infrastructure.database.models import AgentMemoryRecord
from app.infrastructure.database.session import create_session_factory
from app.tools.registry import AgentToolRegistry


class NoopLLM:
    model = "noop"


@pytest.mark.asyncio
async def test_semantic_memory_persists_across_runtime_instances(mysql_engine: AsyncEngine) -> None:
    engine = mysql_engine
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


@pytest.mark.asyncio
async def test_semantic_memory_uses_text_hash_for_deduplication(mysql_engine: AsyncEngine) -> None:
    engine = mysql_engine
    store = PersistentAgentMemoryStore(engine)
    memory = SemanticMemory(text="我的职级是经理，我偏好高铁优先。", source="heuristic", importance=0.85)
    await store.save(agent_id="travel-agent", session_id="s1", user_id="u1", memories=[memory])
    await store.save(agent_id="travel-agent", session_id="s1", user_id="u1", memories=[memory])

    memories = await store.load(agent_id="travel-agent", session_id="s1", user_id="u1")
    factory = create_session_factory(engine)
    async with factory() as session:
        rows = (await session.execute(select(AgentMemoryRecord))).scalars().all()

    assert len(memories) == 1
    assert len(rows) == 1
    assert memories[0].text == "我的职级是经理，我偏好高铁优先。"
    assert len(rows[0].text_hash) == 64
