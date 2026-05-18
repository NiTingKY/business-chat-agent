from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PlanStatus = Literal["planned", "running", "completed", "failed"]
PlanStepStatus = Literal["planned", "running", "completed", "failed", "skipped"]


class PlanStep(BaseModel):
    step_id: str
    index: int
    title: str
    description: str
    suggested_tool: str | None = None
    status: PlanStepStatus = "planned"
    output: dict[str, Any] | None = None
    error: str | None = None


class PlanRun(BaseModel):
    plan_id: str
    turn_id: str
    agent_id: str
    session_id: str | None
    user_id: str | None
    goal: str
    status: PlanStatus = "planned"
    steps: list[PlanStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlanListResponse(BaseModel):
    plans: list[PlanRun]
