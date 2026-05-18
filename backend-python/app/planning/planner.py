from __future__ import annotations

import re
import uuid

from app.domain.schemas import ChatMessage, MessageRole
from app.planning.models import PlanRun, PlanStep


class HeuristicTravelPlanner:
    """Deterministic planner for turning complex travel asks into trackable steps."""

    _PLANNING_KEYWORDS = (
        "规划",
        "安排",
        "行程",
        "出差",
        "差旅",
        "机票",
        "航班",
        "高铁",
        "酒店",
        "住宿",
        "差标",
        "政策",
        "报销",
        "审批",
        "预算",
    )
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

    def should_plan(self, messages: list[ChatMessage]) -> bool:
        goal = self.latest_user_goal(messages)
        if not goal:
            return False
        keyword_hits = sum(1 for keyword in self._PLANNING_KEYWORDS if keyword in goal)
        return keyword_hits >= 2 or len(goal) >= 36

    def build_plan(
        self,
        *,
        turn_id: str,
        agent_id: str,
        session_id: str | None,
        user_id: str | None,
        messages: list[ChatMessage],
    ) -> PlanRun | None:
        goal = self.latest_user_goal(messages)
        if not goal or not self.should_plan(messages):
            return None

        steps = self._steps_for_goal(goal)
        return PlanRun(
            plan_id=str(uuid.uuid4()),
            turn_id=turn_id,
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            goal=goal,
            steps=[
                PlanStep(
                    step_id=str(uuid.uuid4()),
                    index=index,
                    title=step["title"],
                    description=step["description"],
                    suggested_tool=step.get("suggested_tool"),
                )
                for index, step in enumerate(steps, start=1)
            ],
            metadata={
                "planner": "heuristic-travel-planner",
                "detected_entities": self._detect_entities(goal),
            },
        )

    def latest_user_goal(self, messages: list[ChatMessage]) -> str:
        return next((message.content for message in reversed(messages) if message.role is MessageRole.USER), "")

    def format_for_prompt(self, plan: PlanRun) -> str:
        lines = [
            "[Agent plan]",
            f"plan_id: {plan.plan_id}",
            f"goal: {plan.goal}",
            "steps:",
        ]
        for step in plan.steps:
            tool_hint = f" suggested_tool={step.suggested_tool}" if step.suggested_tool else ""
            lines.append(f"{step.index}. {step.title}: {step.description}{tool_hint}")
        return "\n".join(lines)

    def _steps_for_goal(self, goal: str) -> list[dict[str, str | None]]:
        steps: list[dict[str, str | None]] = [
            {
                "title": "澄清差旅约束",
                "description": "识别出发地、目的地、日期、职级、预算、偏好和审批边界；缺失信息需要在回复中追问。",
                "suggested_tool": None,
            }
        ]

        if any(keyword in goal for keyword in ("差标", "政策", "报销", "审批", "预算", "职级")):
            steps.append(
                {
                    "title": "校验差旅政策",
                    "description": "根据员工职级、城市和出行方式校验差标、报销限制与审批要求。",
                    "suggested_tool": "check_travel_policy",
                }
            )

        if any(keyword in goal for keyword in ("行程", "规划", "安排", "出差", "差旅", "机票", "航班", "高铁", "酒店", "住宿")):
            steps.append(
                {
                    "title": "生成候选行程",
                    "description": "组合交通、住宿和日程建议，并避免在用户未提供日期时虚构具体日期。",
                    "suggested_tool": "plan_travel_itinerary",
                }
            )

        steps.append(
            {
                "title": "汇总可执行下一步",
                "description": "输出推荐方案、风险提示、待补充信息和下一步审批或预订动作。",
                "suggested_tool": None,
            }
        )
        return steps

    def _detect_entities(self, goal: str) -> dict[str, list[str]]:
        candidates = [city for city in self._KNOWN_CITIES if city in goal]
        if not candidates:
            city_pattern = re.compile(r"(?:从|到|去|飞往|前往)([\u4e00-\u9fff]{2,4})(?:市)?")
            candidates = [item for item in city_pattern.findall(goal) if item not in self._PLANNING_KEYWORDS]
        return {"city_candidates": candidates[:8]}
