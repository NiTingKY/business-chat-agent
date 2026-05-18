from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.tools.base import AgentTool, ToolNotFoundError


class AgentToolRegistry:
    """Registry used by the runtime chat agent.

    It deliberately exposes OpenAI-compatible schemas, while keeping execution
    behind a single invoke boundary. This is the next step toward a workspace
    skill system where tools are loaded from config rather than hard-coded.
    """

    def __init__(self, tools: Iterable[AgentTool] | None = None) -> None:
        self._tools: dict[str, AgentTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: AgentTool) -> AgentTool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> AgentTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"unknown tool: {name}") from exc

    def list_tools(self, *, enabled_only: bool = True) -> list[AgentTool]:
        tools = list(self._tools.values())
        if enabled_only:
            return [tool for tool in tools if tool.enabled]
        return tools

    def filtered(self, enabled_names: Iterable[str]) -> "AgentToolRegistry":
        allowed = set(enabled_names)
        return AgentToolRegistry(
            tool for tool in self._tools.values() if tool.name in allowed and tool.enabled
        )

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.openai_schema() for tool in self.list_tools()]

    async def invoke(self, name: str, arguments: Mapping[str, Any]) -> str:
        tool = self.get(name)
        if not tool.enabled:
            raise ToolNotFoundError(f"tool disabled: {name}")
        return await tool.invoke(arguments)
