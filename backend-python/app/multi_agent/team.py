from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from app.multi_agent.models import StepAssignment, SubAgentSpec

if TYPE_CHECKING:
    from app.planning.models import PlanStep


class MultiAgentTeam:
    def __init__(self, subagents: list[SubAgentSpec] | tuple[SubAgentSpec, ...]) -> None:
        self._subagents = {agent.role: agent for agent in subagents}

    @classmethod
    def default(cls) -> "MultiAgentTeam":
        return cls(
            [
                SubAgentSpec(
                    agent_id="travel-planner",
                    role="travel_planner",
                    name="Travel Planner",
                    prompt="Clarify constraints, coordinate steps, and produce the final travel action plan.",
                    allowed_tools=(),
                ),
                SubAgentSpec(
                    agent_id="policy-checker",
                    role="policy_checker",
                    name="Policy Checker",
                    prompt="Validate corporate travel policy, reimbursement limits, and approval requirements.",
                    allowed_tools=("check_travel_policy",),
                ),
                SubAgentSpec(
                    agent_id="itinerary-builder",
                    role="itinerary_builder",
                    name="Itinerary Builder",
                    prompt="Build draft itinerary options only when dates and route are explicit.",
                    allowed_tools=("plan_travel_itinerary",),
                ),
                SubAgentSpec(
                    agent_id="expense-reviewer",
                    role="expense_reviewer",
                    name="Expense Reviewer",
                    prompt="Review budget, reimbursement risks, and expense documentation requirements.",
                    allowed_tools=("check_travel_policy",),
                ),
            ]
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MultiAgentTeam":
        path = Path(path)
        if not path.exists():
            return cls.default()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw_agents = data.get("subagents", []) if isinstance(data, dict) else []
        subagents: list[SubAgentSpec] = []
        for raw in raw_agents:
            if not isinstance(raw, dict):
                continue
            subagents.append(
                SubAgentSpec(
                    agent_id=str(raw.get("agent_id") or raw.get("role") or "subagent"),
                    role=str(raw.get("role") or raw.get("agent_id") or "subagent"),
                    name=str(raw.get("name") or raw.get("role") or "Sub Agent"),
                    prompt=str(raw.get("prompt") or ""),
                    allowed_tools=tuple(str(tool) for tool in raw.get("tools", []) or []),
                )
            )
        default_agents = cls.default()._subagents
        merged = {**default_agents, **{agent.role: agent for agent in subagents}}
        return cls(tuple(merged.values()))

    def get(self, role: str) -> SubAgentSpec:
        return self._subagents.get(role) or self._subagents["travel_planner"]

    def assign_step(self, step: "PlanStep") -> StepAssignment:
        role = self._role_for_step(step)
        spec = self.get(role)
        return StepAssignment(
            agent_id=spec.agent_id,
            role=spec.role,
            name=spec.name,
            prompt=spec.prompt,
            allowed_tools=spec.allowed_tools,
            suggested_tool=step.suggested_tool,
        )

    def _role_for_step(self, step: "PlanStep") -> str:
        if step.suggested_tool == "check_travel_policy":
            return "policy_checker"
        if step.suggested_tool == "plan_travel_itinerary":
            return "itinerary_builder"
        text = f"{step.title} {step.description}"
        if any(keyword in text for keyword in ("预算", "报销", "费用", "expense", "budget")):
            return "expense_reviewer"
        return "travel_planner"

    def to_prompt_block(self) -> str:
        lines = ["[Sub-agents]"]
        for spec in self._subagents.values():
            tools = ", ".join(spec.allowed_tools) if spec.allowed_tools else "none"
            lines.append(f"- {spec.role} ({spec.agent_id}): tools={tools}; prompt={spec.prompt}")
        return "\n".join(lines)
