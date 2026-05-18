from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.session import AgentSession
from app.agent_runtime.turn import AgentTurnContext
from app.domain.schemas import ChatMessage, MessageRole
from app.planning import HeuristicTravelPlanner, PersistentPlanStore
from app.planning.executor import PlanStepExecutor
from app.tools.travel import default_travel_tool_registry


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
            "model": "fake-plan-executor",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "执行图已处理。"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


def _build_plan(content: str):
    planner = HeuristicTravelPlanner()
    plan = planner.build_plan(
        turn_id="turn-executor",
        agent_id="travel-agent",
        session_id="s-executor",
        user_id="u-executor",
        messages=[ChatMessage(role=MessageRole.USER, content=content)],
    )
    assert plan is not None
    return plan


@pytest.mark.asyncio
async def test_executor_completes_tool_steps_when_inputs_are_present() -> None:
    plan = _build_plan(
        "我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，预算3000元，检查差标和审批要求。"
    )
    executor = PlanStepExecutor(default_travel_tool_registry())

    executed = await executor.execute(plan)

    statuses = {step.suggested_tool: step.status for step in executed.steps}
    assert statuses["check_travel_policy"] == "completed"
    assert statuses["plan_travel_itinerary"] == "completed"
    policy_step = next(step for step in executed.steps if step.suggested_tool == "check_travel_policy")
    itinerary_step = next(step for step in executed.steps if step.suggested_tool == "plan_travel_itinerary")
    assert policy_step.output is not None
    assert policy_step.output["tool_name"] == "check_travel_policy"
    assert itinerary_step.output is not None
    assert itinerary_step.output["tool_name"] == "plan_travel_itinerary"
    assert executed.status == "completed"


@pytest.mark.asyncio
async def test_executor_skips_tool_steps_when_date_is_missing() -> None:
    plan = _build_plan("我是经理，帮我规划北京到上海的出差行程，并检查差标和审批要求。")
    executor = PlanStepExecutor(default_travel_tool_registry())

    executed = await executor.execute(plan)

    tool_steps = [step for step in executed.steps if step.suggested_tool]
    assert tool_steps
    assert all(step.status == "skipped" for step in tool_steps)
    assert all(step.error and "departure_date" in step.error for step in tool_steps)
    assert executed.status == "completed"


@pytest.mark.asyncio
async def test_plan_store_persists_execution_result(mysql_engine: AsyncEngine) -> None:
    engine = mysql_engine
    plan = _build_plan(
        "我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，预算3000元，检查差标。"
    )
    store = PersistentPlanStore(engine)
    executor = PlanStepExecutor(default_travel_tool_registry())

    await store.save_plan(plan)
    executed = await executor.execute(plan)
    await store.save_execution_result(executed)
    loaded = await store.get_plan(plan.plan_id)

    assert loaded is not None
    assert loaded.status == "completed"
    assert any(step.status == "completed" and step.output for step in loaded.steps)


@pytest.mark.asyncio
async def test_runtime_executes_plan_steps_and_injects_summary(mysql_engine: AsyncEngine) -> None:
    engine = mysql_engine
    orchestrator = FakeOrchestrator()
    plan_store = PersistentPlanStore(engine)
    runtime = AgentRuntime(
        agent_id="travel-agent",
        orchestrator=orchestrator,  # type: ignore[arg-type]
        sessions=FakeSessions(),  # type: ignore[arg-type]
        plan_store=plan_store,
        plan_executor=PlanStepExecutor(default_travel_tool_registry()),
    )

    result = await runtime.run_turn(
        AgentTurnContext(
            agent_id="travel-agent",
            session_id="s-runtime-executor",
            user_id="u-runtime-executor",
            messages=[
                ChatMessage(
                    role=MessageRole.USER,
                    content=(
                        "我是经理，帮我规划北京到上海的出差行程，"
                        "出发日期是2026-06-01，预算3000元，检查差标和审批要求。"
                    ),
                )
            ],
        )
    )

    plan_event = next(event for event in result.events if event["type"] == "plan.created")
    loaded = await plan_store.get_plan(plan_event["payload"]["plan_id"])

    assert loaded is not None
    assert loaded.status == "completed"
    assert any(step.suggested_tool == "check_travel_policy" and step.status == "completed" for step in loaded.steps)
    assert any(step.suggested_tool == "plan_travel_itinerary" and step.status == "completed" for step in loaded.steps)
    assert "[Plan execution]" in orchestrator.received[-2].content
    assert any(event["type"] == "plan.step.completed" for event in result.events)
    assert any(event["type"] == "plan.completed" for event in result.events)
