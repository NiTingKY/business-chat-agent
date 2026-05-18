from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


ToolHandler = Callable[[Mapping[str, Any]], Awaitable[str] | str]


@dataclass(slots=True)
class AgentTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    enabled: bool = True
    tags: set[str] = field(default_factory=set)

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def invoke(self, arguments: Mapping[str, Any]) -> str:
        result = self.handler(arguments)
        if inspect.isawaitable(result):
            result = await result
        return str(result)


class ToolNotFoundError(KeyError):
    pass

