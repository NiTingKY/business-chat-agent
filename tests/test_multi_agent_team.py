from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.schemas import ChatMessage, MessageRole
from app.main import create_app
from app.multi_agent.team import MultiAgentTeam
from app.planning import HeuristicTravelPlanner
from app.planning.executor import PlanStepExecutor
from app.tools.travel import default_travel_tool_registry


def _build_plan(content: str):
    planner = HeuristicTravelPlanner()
    plan = planner.build_plan(
        turn_id="turn-team",
        agent_id="travel-agent",
        session_id="s-team",
        user_id="u-team",
        messages=[ChatMessage(role=MessageRole.USER, content=content)],
    )
    assert plan is not None
    return plan


def test_default_team_routes_steps_to_specialized_roles() -> None:
    team = MultiAgentTeam.default()
    plan = _build_plan(
        "我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，预算3000元，检查差标和审批要求。"
    )

    assignments = [team.assign_step(step) for step in plan.steps]

    roles = {assignment.role for assignment in assignments}
    assert "travel_planner" in roles
    assert "policy_checker" in roles
    assert "itinerary_builder" in roles
    policy_assignment = next(item for item in assignments if item.suggested_tool == "check_travel_policy")
    assert policy_assignment.agent_id == "policy-checker"
    assert "check_travel_policy" in policy_assignment.allowed_tools


def test_team_loads_subagents_from_workspace_yaml(tmp_path: Path) -> None:
    config = tmp_path / "subagents.yaml"
    config.write_text(
        """
subagents:
  - agent_id: custom-policy
    role: policy_checker
    name: Custom Policy Checker
    prompt: Only validate policy.
    tools:
      - check_travel_policy
  - agent_id: custom-itinerary
    role: itinerary_builder
    name: Custom Itinerary Builder
    prompt: Only build itinerary.
    tools:
      - plan_travel_itinerary
""",
        encoding="utf-8",
    )

    team = MultiAgentTeam.from_yaml(config)

    assert team.get("policy_checker").agent_id == "custom-policy"
    assert team.get("itinerary_builder").allowed_tools == ("plan_travel_itinerary",)


@pytest.mark.asyncio
async def test_executor_writes_assigned_agent_metadata() -> None:
    plan = _build_plan(
        "我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，预算3000元，检查差标和审批要求。"
    )
    executor = PlanStepExecutor(default_travel_tool_registry(), team=MultiAgentTeam.default())

    executed = await executor.execute(plan)

    tool_steps = [step for step in executed.steps if step.suggested_tool]
    assert tool_steps
    assert all(step.output for step in tool_steps)
    assert {step.output["agent_role"] for step in tool_steps} == {
        "policy_checker",
        "itinerary_builder",
    }
    assert all("assigned_agent" in step.output for step in tool_steps)


@pytest.mark.asyncio
async def test_executor_fails_step_when_assigned_agent_lacks_tool_permission(tmp_path: Path) -> None:
    config = tmp_path / "subagents.yaml"
    config.write_text(
        """
subagents:
  - agent_id: restricted-policy
    role: policy_checker
    name: Restricted Policy
    prompt: No tools are allowed.
    tools: []
""",
        encoding="utf-8",
    )
    plan = _build_plan(
        "我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，预算3000元，检查差标和审批要求。"
    )
    executor = PlanStepExecutor(default_travel_tool_registry(), team=MultiAgentTeam.from_yaml(config))

    executed = await executor.execute(plan)

    policy_step = next(step for step in executed.steps if step.suggested_tool == "check_travel_policy")
    assert policy_step.status == "failed"
    assert policy_step.error is not None
    assert "not allowed" in policy_step.error


def test_app_loads_workspace_subagents() -> None:
    app = create_app()
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        team = app.state.multi_agent_team
        assert team.get("policy_checker").agent_id == "policy-checker"
        assert "check_travel_policy" in team.get("policy_checker").allowed_tools
