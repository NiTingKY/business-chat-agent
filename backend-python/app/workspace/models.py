from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.agent_runtime.agent_config import AgentConfig


@dataclass(frozen=True, slots=True)
class SkillSpec:
    skill_id: str
    name: str
    description: str
    prompt: str
    tools: tuple[str, ...] = field(default_factory=tuple)
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class AgentWorkspace:
    config: AgentConfig
    system_prompt: str
    skills: tuple[SkillSpec, ...] = field(default_factory=tuple)
    path: Path | None = None

