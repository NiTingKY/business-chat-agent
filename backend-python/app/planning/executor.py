from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.multi_agent.models import StepAssignment
from app.multi_agent.team import MultiAgentTeam
from app.planning.models import PlanRun, PlanStep
from app.tools.registry import AgentToolRegistry


@dataclass(slots=True)
class ExtractedTravelInputs:
    employee_id: str = "unknown"
    grade: str = "staff"
    origin_city: str | None = None
    destination_city: str | None = None
    departure_date: str | None = None
    return_date: str | None = None
    estimated_total_cny: float | None = None
    purpose: str = "client_visit"
    preferred_class: str | None = None


class PlanStepExecutor:
    """Executes deterministic plan steps when tool inputs are explicit enough."""

    _KNOWN_CITIES = (
        "北京",
        "上海",
        "广州",
        "深圳",
        "杭州",
        "南京",
        "成都",
        "重庆",
        "武汉",
        "西安",
        "苏州",
        "天津",
        "青岛",
        "厦门",
        "长沙",
        "郑州",
    )

    def __init__(self, tools: AgentToolRegistry, *, team: MultiAgentTeam | None = None) -> None:
        self._tools = tools
        self._team = team or MultiAgentTeam.default()

    async def execute(self, plan: PlanRun) -> PlanRun:
        inputs = self._extract_inputs(plan.goal)
        for step in plan.steps:
            assignment = self._team.assign_step(step)
            if not step.suggested_tool:
                self._complete_local_step(step, assignment)
                continue
            await self._execute_tool_step(step, inputs, assignment)

        if any(step.status == "failed" for step in plan.steps):
            plan.status = "failed"
        else:
            plan.status = "completed"
        return plan

    def format_execution_summary(self, plan: PlanRun) -> str:
        lines = [
            "[Plan execution]",
            f"plan_id: {plan.plan_id}",
            f"status: {plan.status}",
        ]
        for step in plan.steps:
            preview = ""
            if step.output:
                preview = f" output={str(step.output.get('result_preview', ''))[:240]}"
            if step.error:
                preview = f" error={step.error}"
            lines.append(f"{step.index}. {step.title} [{step.status}]{preview}")
        return "\n".join(lines)

    async def _execute_tool_step(
        self,
        step: PlanStep,
        inputs: ExtractedTravelInputs,
        assignment: StepAssignment,
    ) -> None:
        step.status = "running"
        if step.suggested_tool not in assignment.allowed_tools:
            step.status = "failed"
            step.error = f"tool {step.suggested_tool} is not allowed for sub-agent {assignment.agent_id}"
            step.output = self._assignment_output(assignment)
            return

        arguments, missing = self._arguments_for_tool(step.suggested_tool or "", inputs)
        if missing:
            step.status = "skipped"
            step.error = "missing required inputs: " + ", ".join(missing)
            step.output = self._assignment_output(assignment)
            return

        try:
            result = await self._tools.invoke(step.suggested_tool or "", arguments)
        except Exception as exc:
            step.status = "failed"
            step.error = str(exc)
            return

        step.status = "completed"
        step.output = {
            **self._assignment_output(assignment),
            "tool_name": step.suggested_tool,
            "arguments": arguments,
            "result_preview": result[:1000],
        }
        step.error = None

    def _complete_local_step(self, step: PlanStep, assignment: StepAssignment) -> None:
        step.status = "completed"
        step.output = {
            **self._assignment_output(assignment),
            "note": "local planning step completed",
            "description": step.description,
        }
        step.error = None

    @staticmethod
    def _assignment_output(assignment: StepAssignment) -> dict[str, Any]:
        return {
            "assigned_agent": assignment.agent_id,
            "agent_role": assignment.role,
            "agent_name": assignment.name,
            "agent_prompt": assignment.prompt,
            "allowed_tools": list(assignment.allowed_tools),
        }

    def _arguments_for_tool(
        self,
        tool_name: str,
        inputs: ExtractedTravelInputs,
    ) -> tuple[dict[str, Any], list[str]]:
        common: dict[str, Any] = {
            "employee_id": inputs.employee_id,
            "grade": inputs.grade,
            "origin_city": inputs.origin_city,
            "destination_city": inputs.destination_city,
            "departure_date": inputs.departure_date,
        }
        missing = [
            name
            for name in ("origin_city", "destination_city", "departure_date")
            if common.get(name) in (None, "")
        ]
        if inputs.return_date:
            common["return_date"] = inputs.return_date
        if inputs.preferred_class:
            common["preferred_class"] = inputs.preferred_class

        if tool_name == "plan_travel_itinerary":
            return {**common, "purpose": inputs.purpose}, missing

        if tool_name == "check_travel_policy":
            if inputs.estimated_total_cny is None:
                missing.append("estimated_total_cny")
            return {
                **common,
                "estimated_total_cny": inputs.estimated_total_cny,
            }, missing

        return common, [f"unsupported tool: {tool_name}"]

    def _extract_inputs(self, goal: str) -> ExtractedTravelInputs:
        cities = [city for city in self._KNOWN_CITIES if city in goal]
        dates = re.findall(r"(20\d{2}-\d{2}-\d{2})", goal)
        budget = self._extract_budget(goal)
        return ExtractedTravelInputs(
            grade=self._extract_grade(goal),
            origin_city=cities[0] if len(cities) >= 1 else None,
            destination_city=cities[1] if len(cities) >= 2 else None,
            departure_date=dates[0] if dates else None,
            return_date=dates[1] if len(dates) >= 2 else None,
            estimated_total_cny=budget,
            preferred_class=self._extract_preferred_class(goal),
        )

    def _extract_grade(self, goal: str) -> str:
        lower = goal.lower()
        if any(text in lower for text in ("executive", "高管", "vp", "总裁")):
            return "executive"
        if any(text in lower for text in ("director", "总监")):
            return "director"
        if any(text in lower for text in ("manager", "经理")):
            return "manager"
        return "staff"

    def _extract_budget(self, goal: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|cny|CNY|人民币)", goal)
        return float(match.group(1)) if match else None

    def _extract_preferred_class(self, goal: str) -> str | None:
        lower = goal.lower()
        if "商务舱" in goal or "business" in lower:
            return "business"
        if "高端经济舱" in goal or "premium" in lower:
            return "premium_economy"
        if "经济舱" in goal or "economy" in lower:
            return "economy"
        return None
