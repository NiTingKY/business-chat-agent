from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubAgentSpec:
    agent_id: str
    role: str
    name: str
    prompt: str
    allowed_tools: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StepAssignment:
    agent_id: str
    role: str
    name: str
    prompt: str
    allowed_tools: tuple[str, ...]
    suggested_tool: str | None = None
