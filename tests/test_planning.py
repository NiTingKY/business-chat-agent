from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.session import AgentSession
from app.agent_runtime.turn import AgentTurnContext
from app.domain.schemas import ChatMessage, MessageRole, StreamChunk
from app.infrastructure.database.models import Base
from app.infrastructure.database.session import create_async_db_engine
from app.planning import HeuristicTravelPlanner, PersistentPlanStore


class FakeSessions:
    async def load(self, session_id: str | None, user_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id or "", user_id=user_id, history=[])

    async def save_message(
        self,
        *,
        session_id: str | None,
        user_id: str | None,
        role: MessageRole | str,
        content: str,
    ) -> None:
        return None


class FakeOrchestrator:
    def __init__(self) -> None:
        self.received: list[ChatMessage] = []

    async def run_completion(
        self,
        messages: list[ChatMessage],
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        self.received = list(messages)
        return {
            "id": str(uuid.uuid4()),
            "created": int(time.time()),
            "model": "fake-plan",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "计划已生成。"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def stream_completion(
        self,
        messages: list[ChatMessage],
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        return
        yield


def test_heuristic_planner_builds_travel_steps() -> None:
    planner = HeuristicTravelPlanner()
    messages = [
        ChatMessage(
            role=MessageRole.USER,
            content="帮我规划北京到上海的出差行程，顺便检查经理职级的差标和审批要求。",
        )
    ]

    plan = planner.build_plan(
        turn_id="turn-1",
        agent_id="travel-agent",
        session_id="s1",
        user_id="u1",
        messages=messages,
    )

    assert plan is not None
    assert plan.goal.startswith("帮我规划北京到上海")
    assert [step.suggested_tool for step in plan.steps] == [
        None,
        "check_travel_policy",
        "plan_travel_itinerary",
        None,
    ]
    assert "北京" in plan.metadata["detected_entities"]["city_candidates"]


@pytest.mark.asyncio
async def test_plan_store_saves_and_loads_steps(tmp_path: Path) -> None:
    engine = create_async_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'plans.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    planner = HeuristicTravelPlanner()
    plan = planner.build_plan(
        turn_id="turn-store",
        agent_id="travel-agent",
        session_id="s-store",
        user_id="u-store",
        messages=[
            ChatMessage(
                role=MessageRole.USER,
                content="请安排广州到深圳的差旅行程，并检查报销政策。",
            )
        ],
    )
    assert plan is not None

    store = PersistentPlanStore(engine)
    await store.save_plan(plan)
    loaded = await store.get_plan(plan.plan_id)

    assert loaded is not None
    assert loaded.plan_id == plan.plan_id
    assert len(loaded.steps) == len(plan.steps)
    assert loaded.steps[1].suggested_tool == "check_travel_policy"
    await engine.dispose()


@pytest.mark.asyncio
async def test_runtime_creates_plan_for_complex_turn(tmp_path: Path) -> None:
    engine = create_async_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'runtime-plans.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    orchestrator = FakeOrchestrator()
    plan_store = PersistentPlanStore(engine)
    runtime = AgentRuntime(
        agent_id="travel-agent",
        orchestrator=orchestrator,  # type: ignore[arg-type]
        sessions=FakeSessions(),  # type: ignore[arg-type]
        plan_store=plan_store,
    )

    result = await runtime.run_turn(
        AgentTurnContext(
            agent_id="travel-agent",
            session_id="s-runtime",
            user_id="u-runtime",
            messages=[
                ChatMessage(
                    role=MessageRole.USER,
                    content="帮我规划北京到上海的出差行程，检查差标、酒店、交通和审批要求。",
                )
            ],
        )
    )

    assert orchestrator.received[0].role is MessageRole.SYSTEM
    assert orchestrator.received[0].content.startswith("[Agent plan]")
    plan_id = result.events[0]["payload"].get("metadata", {}).get("plan_id")
    if plan_id is None:
        plan_id = next(event["payload"]["plan_id"] for event in result.events if event["type"] == "plan.created")
    loaded = await plan_store.get_plan(plan_id)
    assert loaded is not None
    assert len(loaded.steps) >= 3
    assert any(event["type"] == "plan.step.created" for event in result.events)
    await engine.dispose()
