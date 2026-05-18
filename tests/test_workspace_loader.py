from __future__ import annotations

from pathlib import Path

from app.tools.travel import default_travel_tool_registry
from app.workspace.loader import WorkspaceLoader


def test_workspace_loader_loads_agent_and_skills() -> None:
    workspace = WorkspaceLoader("workspace").load_agent(
        "travel-agent",
        fallback_model="fallback-model",
    )

    assert workspace.config.agent_id == "travel-agent"
    assert workspace.config.model == "Qwen/Qwen3-8B"
    assert workspace.config.enabled_tools == ("plan_travel_itinerary", "check_travel_policy")
    assert {skill.skill_id for skill in workspace.skills} == {"travel-policy", "expense-control"}
    assert "你是企业差旅智能体" in workspace.system_prompt
    assert "[Skill: travel-policy]" in workspace.system_prompt
    assert "不要把模型自己生成的日期" in workspace.system_prompt


def test_workspace_loader_falls_back_when_agent_missing(tmp_path: Path) -> None:
    workspace = WorkspaceLoader(tmp_path).load_agent("missing-agent", fallback_model="gpt-test")

    assert workspace.config.agent_id == "travel-agent"
    assert workspace.config.model == "gpt-test"
    assert workspace.skills == ()


def test_workspace_tool_filter_uses_agent_enabled_tools() -> None:
    workspace = WorkspaceLoader("workspace").load_agent(
        "travel-agent",
        fallback_model="fallback-model",
    )
    registry = default_travel_tool_registry().filtered(workspace.config.enabled_tools)

    assert {tool.name for tool in registry.list_tools()} == {
        "plan_travel_itinerary",
        "check_travel_policy",
    }
