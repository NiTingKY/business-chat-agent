from __future__ import annotations

import pytest

from app.domain.schemas import ChatMessage, MessageRole
from app.multi_agent import MultiAgentTeam
from app.planning import HeuristicTravelPlanner
from app.planning.executor import PlanStepExecutor
from app.tools.travel import default_travel_tool_registry


def test_real_chinese_request_creates_policy_and_itinerary_steps() -> None:
    planner = HeuristicTravelPlanner()
    plan = planner.build_plan(
        turn_id="turn-real-cn",
        agent_id="travel-agent",
        session_id="s-real-cn",
        user_id="u-real-cn",
        messages=[
            ChatMessage(
                role=MessageRole.USER,
                content="我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，预算3000元，检查差标和审批要求。",
            )
        ],
    )

    assert plan is not None
    assert "北京" in plan.metadata["detected_entities"]["city_candidates"]
    assert "上海" in plan.metadata["detected_entities"]["city_candidates"]
    assert [step.suggested_tool for step in plan.steps] == [
        None,
        "check_travel_policy",
        "plan_travel_itinerary",
        None,
    ]


@pytest.mark.asyncio
async def test_real_chinese_request_executes_specialized_subagents() -> None:
    planner = HeuristicTravelPlanner()
    plan = planner.build_plan(
        turn_id="turn-real-cn-exec",
        agent_id="travel-agent",
        session_id="s-real-cn-exec",
        user_id="u-real-cn-exec",
        messages=[
            ChatMessage(
                role=MessageRole.USER,
                content="我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，预算3000元，检查差标和审批要求。",
            )
        ],
    )
    assert plan is not None

    executed = await PlanStepExecutor(
        default_travel_tool_registry(),
        team=MultiAgentTeam.default(),
    ).execute(plan)

    roles = {step.output.get("agent_role") for step in executed.steps if step.output}
    assert "policy_checker" in roles
    assert "itinerary_builder" in roles
    assert any(step.suggested_tool == "check_travel_policy" and step.status == "completed" for step in executed.steps)
    assert any(step.suggested_tool == "plan_travel_itinerary" and step.status == "completed" for step in executed.steps)
