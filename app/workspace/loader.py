from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.agent_runtime.agent_config import AgentConfig, default_travel_agent_config
from app.workspace.models import AgentWorkspace, SkillSpec


class WorkspaceLoadError(RuntimeError):
    pass


class WorkspaceLoader:
    """Loads OpenClaw-style agent and skill files from a workspace directory."""

    def __init__(self, root: str | Path = "workspace") -> None:
        self.root = Path(root)

    def load_agent(self, agent_id: str, *, fallback_model: str) -> AgentWorkspace:
        agent_dir = self.root / "agents" / agent_id
        if not agent_dir.exists():
            config = default_travel_agent_config(fallback_model)
            return AgentWorkspace(config=config, system_prompt=config.system_prompt)

        raw = self._read_yaml(agent_dir / "agent.yaml")
        enabled_skills = tuple(str(x) for x in raw.get("skills", []) or [])
        base_prompt = self._read_text(agent_dir / "SYSTEM.md")
        skills = tuple(self.load_skill(skill_id) for skill_id in enabled_skills)
        system_prompt = self.compose_system_prompt(base_prompt, skills)
        config = AgentConfig(
            agent_id=str(raw.get("agent_id") or agent_id),
            name=str(raw.get("name") or agent_id),
            model=str(raw.get("model") or fallback_model),
            enabled_tools=tuple(str(x) for x in raw.get("tools", []) or []),
            enabled_skills=enabled_skills,
            system_prompt=system_prompt,
            memory_backend=str(raw.get("memory_backend") or "sqlite"),
            vector_backend=str(raw.get("vector_backend") or "milvus-or-memory"),
        )
        return AgentWorkspace(config=config, system_prompt=system_prompt, skills=skills, path=agent_dir)

    def load_skill(self, skill_id: str) -> SkillSpec:
        skill_dir = self.root / "skills" / skill_id
        if not skill_dir.exists():
            raise WorkspaceLoadError(f"skill not found: {skill_id}")
        raw = self._read_yaml(skill_dir / "skill.yaml")
        return SkillSpec(
            skill_id=str(raw.get("skill_id") or skill_id),
            name=str(raw.get("name") or skill_id),
            description=str(raw.get("description") or ""),
            prompt=self._read_text(skill_dir / "SKILL.md"),
            tools=tuple(str(x) for x in raw.get("tools", []) or []),
            path=skill_dir,
        )

    @staticmethod
    def compose_system_prompt(base_prompt: str, skills: tuple[SkillSpec, ...]) -> str:
        parts = [base_prompt.strip()]
        for skill in skills:
            parts.append(f"[Skill: {skill.skill_id}]\n{skill.prompt.strip()}")
        return "\n\n".join(part for part in parts if part)

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise WorkspaceLoadError(f"missing workspace file: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise WorkspaceLoadError(f"workspace file must contain a mapping: {path}")
        return data

    @staticmethod
    def _read_text(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

