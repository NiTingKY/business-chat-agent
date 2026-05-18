from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.agent_runtime.turn import AgentTurnContext, AgentTurnResult
from app.main import create_app
from app.scheduler.service import AgentSchedulerService
from sqlalchemy.ext.asyncio import AsyncEngine


class FakeRuntime:
    def __init__(self) -> None:
        self.contexts: list[AgentTurnContext] = []

    async def run_turn(self, context: AgentTurnContext) -> AgentTurnResult:
        self.contexts.append(context)
        return AgentTurnResult(
            turn_id=context.turn_id,
            raw_response={
                "id": str(uuid.uuid4()),
                "created": int(time.time()),
                "model": "fake-scheduler",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "已执行计划任务",
                        },
                    }
                ],
            },
            session_id=context.session_id,
            events=[],
        )


@pytest.mark.asyncio
async def test_scheduler_runs_due_job_through_runtime(mysql_engine: AsyncEngine) -> None:
    engine = mysql_engine
    scheduler = AgentSchedulerService(engine)
    runtime = FakeRuntime()
    job = await scheduler.create_job(
        agent_id="travel-agent",
        session_id="schedule-s1",
        user_id="schedule-u1",
        prompt="明天上午提醒我检查上海出差政策。",
        run_at=datetime.utcnow() - timedelta(seconds=1),
        metadata={"source": "test"},
    )

    assert job["status"] == "pending"
    completed = await scheduler.run_due_once(runtime)  # type: ignore[arg-type]

    assert len(completed) == 1
    assert completed[0]["status"] == "completed"
    assert completed[0]["result"]["assistant_content"] == "已执行计划任务"
    assert runtime.contexts[0].channel == "scheduler"
    assert runtime.contexts[0].metadata["job_id"] == job["job_id"]
    assert runtime.contexts[0].messages[0].content.startswith("[Scheduled task]")


def test_scheduler_api_creates_lists_and_runs_due_job() -> None:
    app = create_app()
    session_id = f"scheduler-api-{uuid.uuid4()}"
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/scheduler/jobs",
            json={
                "session_id": session_id,
                "user_id": "scheduler-user",
                "prompt": "提醒我整理本周出差报销材料。",
                "run_at": (datetime.utcnow() - timedelta(seconds=1)).isoformat(),
                "metadata": {"source": "api-test"},
            },
        )
        assert created.status_code == 200
        job_id = created.json()["job_id"]

        listed = client.get("/api/v1/scheduler/jobs", params={"session_id": session_id})
        assert listed.status_code == 200
        assert any(job["job_id"] == job_id for job in listed.json()["jobs"])

        fake_runtime = FakeRuntime()
        app.state.agent_runtime = fake_runtime
        ran = client.post("/api/v1/scheduler/run-due")
        assert ran.status_code == 200
        assert ran.json()["ran"] >= 1
        assert any(job["job_id"] == job_id and job["status"] == "completed" for job in ran.json()["jobs"])
        assert fake_runtime.contexts
