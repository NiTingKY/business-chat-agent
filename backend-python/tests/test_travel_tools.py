from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.agent.orchestrator import TravelOrchestrator


@pytest.mark.asyncio
async def test_plan_tool_rejects_past_departure_date() -> None:
    orchestrator = TravelOrchestrator()

    result = await orchestrator._execute_tool(
        "plan_travel_itinerary",
        json.dumps(
            {
                "employee_id": "u1",
                "grade": "manager",
                "origin_city": "北京",
                "destination_city": "上海",
                "departure_date": "2023-01-01",
                "purpose": "client_visit",
            }
        ),
    )

    assert "早于今天" in result
    assert "不要声称用户提供了该日期" in result


@pytest.mark.asyncio
async def test_plan_tool_returns_clean_chinese_itinerary_for_future_date() -> None:
    orchestrator = TravelOrchestrator()
    departure = (date.today() + timedelta(days=10)).isoformat()

    result = await orchestrator._execute_tool(
        "plan_travel_itinerary",
        json.dumps(
            {
                "employee_id": "u1",
                "grade": "manager",
                "origin_city": "北京",
                "destination_city": "上海",
                "departure_date": departure,
                "purpose": "client_visit",
                "preferred_class": "premium_economy",
            },
            ensure_ascii=False,
        ),
    )

    assert "北京 -> 上海 商务行程" in result
    assert "预计总额" in result
    assert "差标提示" in result
