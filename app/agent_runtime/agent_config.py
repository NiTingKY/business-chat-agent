from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentConfig:
    agent_id: str
    name: str
    model: str
    enabled_tools: tuple[str, ...] = field(default_factory=tuple)
    enabled_skills: tuple[str, ...] = field(default_factory=tuple)
    system_prompt: str = ""
    memory_backend: str = "sqlite"
    vector_backend: str = "milvus-or-memory"


def default_travel_agent_config(model: str) -> AgentConfig:
    return AgentConfig(
        agent_id="travel-agent",
        name="商旅 Agent",
        model=model,
        enabled_tools=("plan_travel_itinerary", "check_travel_policy"),
        enabled_skills=("travel-policy", "expense-control"),
    )
