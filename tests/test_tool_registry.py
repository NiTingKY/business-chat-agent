from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

import pytest

from app.agent.orchestrator import TravelOrchestrator
from app.tools.base import AgentTool, ToolNotFoundError
from app.tools.registry import AgentToolRegistry
from app.tools.travel import default_travel_tool_registry


@pytest.mark.asyncio
async def test_default_travel_registry_exposes_openai_tool_schemas() -> None:
    registry = default_travel_tool_registry()
    schemas = registry.openai_tools()

    names = {schema["function"]["name"] for schema in schemas}
    assert "plan_travel_itinerary" in names
    assert "check_travel_policy" in names
    plan_schema = next(s for s in schemas if s["function"]["name"] == "plan_travel_itinerary")
    assert "departure_date" in plan_schema["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_registry_invokes_travel_tool() -> None:
    registry = default_travel_tool_registry()
    departure = (date.today() + timedelta(days=8)).isoformat()

    result = await registry.invoke(
        "plan_travel_itinerary",
        {
            "employee_id": "u1",
            "grade": "manager",
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": departure,
            "purpose": "client_visit",
        },
    )

    assert "北京 -> 上海 商务行程" in result
    assert "预计总额" in result


@pytest.mark.asyncio
async def test_registry_blocks_disabled_tool() -> None:
    async def handler(arguments: Mapping[str, Any]) -> str:
        return "ok"

    registry = AgentToolRegistry(
        [
            AgentTool(
                name="disabled_tool",
                description="disabled",
                parameters={"type": "object", "properties": {}},
                handler=handler,
                enabled=False,
            )
        ]
    )

    with pytest.raises(ToolNotFoundError):
        await registry.invoke("disabled_tool", {})


@pytest.mark.asyncio
async def test_orchestrator_executes_tools_via_registry() -> None:
    calls: list[tuple[str, Mapping[str, Any]]] = []

    async def handler(arguments: Mapping[str, Any]) -> str:
        calls.append(("custom_plan", dict(arguments)))
        return "custom result"

    registry = AgentToolRegistry(
        [
            AgentTool(
                name="plan_travel_itinerary",
                description="custom",
                parameters={"type": "object", "properties": {}},
                handler=handler,
            )
        ]
    )
    orchestrator = TravelOrchestrator(tool_registry=registry)

    result = await orchestrator._execute_tool(
        "plan_travel_itinerary",
        json.dumps({"origin_city": "北京"}, ensure_ascii=False),
    )

    assert result == "custom result"
    assert calls == [("custom_plan", {"origin_city": "北京"})]
