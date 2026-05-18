from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.turn import AgentTurnContext
from app.domain.schemas import ChatMessage, MessageRole
from app.infrastructure.database.models import AgentScheduledJobRecord
from app.infrastructure.database.repository import AgentSchedulerRepository
from app.infrastructure.database.session import create_session_factory


class AgentSchedulerService:
    """Small event-driven scheduler for delayed agent turns."""

    def __init__(self, engine: AsyncEngine | None):
        self._engine = engine
        self._session_factory = create_session_factory(engine) if engine is not None else None
        self._stop = asyncio.Event()

    async def create_job(
        self,
        *,
        agent_id: str,
        session_id: str | None,
        user_id: str | None,
        prompt: str,
        run_at: datetime,
        job_type: str = "agent_turn",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._ensure_available()
        normalized_run_at = self._normalize_datetime(run_at)
        async with self._session_factory() as session:  # type: ignore[misc]
            record = await AgentSchedulerRepository(session).create_job(
                job_id=str(uuid.uuid4()),
                agent_id=agent_id,
                session_id=session_id,
                user_id=user_id,
                job_type=job_type,
                prompt=prompt,
                run_at=normalized_run_at,
                metadata=metadata,
            )
            return self._to_dict(record)

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self._session_factory is None:
            return []
        async with self._session_factory() as session:
            records = await AgentSchedulerRepository(session).list_jobs(
                status=status,
                session_id=session_id,
                agent_id=agent_id,
                limit=limit,
            )
            return [self._to_dict(record) for record in records]

    async def run_due_once(
        self,
        runtime: AgentRuntime,
        *,
        now: datetime | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if self._session_factory is None:
            return []
        now = self._normalize_datetime(now or datetime.utcnow())
        async with self._session_factory() as session:
            due_jobs = await AgentSchedulerRepository(session).list_due_jobs(now=now, limit=limit)

        completed: list[dict[str, Any]] = []
        for job in due_jobs:
            updated = await self._mark_running(job.job_id)
            if updated is None:
                continue
            completed.append(await self._execute_job(runtime, updated))
        return completed

    async def poll_loop(
        self,
        runtime: AgentRuntime,
        *,
        interval_seconds: float = 30.0,
        limit: int = 20,
    ) -> None:
        while not self._stop.is_set():
            try:
                await self.run_due_once(runtime, limit=limit)
            except Exception:
                # The next tick can recover; individual job failures are stored by _execute_job.
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop.set()

    async def _execute_job(self, runtime: AgentRuntime, job: dict[str, Any]) -> dict[str, Any]:
        try:
            if job["job_type"] != "agent_turn":
                raise ValueError(f"Unsupported scheduled job type: {job['job_type']}")
            result = await runtime.run_turn(
                AgentTurnContext(
                    agent_id=job["agent_id"],
                    session_id=job["session_id"],
                    user_id=job["user_id"],
                    channel="scheduler",
                    messages=[
                        ChatMessage(
                            role=MessageRole.USER,
                            content=f"[Scheduled task]\n{job['prompt']}",
                        )
                    ],
                    metadata={
                        "job_id": job["job_id"],
                        "job_type": job["job_type"],
                        **(job.get("metadata") or {}),
                    },
                )
            )
            assistant_content = result.raw_response["choices"][0]["message"]["content"]
            payload = {
                "turn_id": result.turn_id,
                "session_id": result.session_id,
                "assistant_content": assistant_content,
            }
            return await self._mark_completed(job["job_id"], payload)
        except Exception as exc:
            return await self._mark_failed(job["job_id"], str(exc))

    async def _mark_running(self, job_id: str) -> dict[str, Any] | None:
        self._ensure_available()
        async with self._session_factory() as session:  # type: ignore[misc]
            record = await AgentSchedulerRepository(session).mark_running(job_id)
            return self._to_dict(record) if record is not None else None

    async def _mark_completed(self, job_id: str, result: dict[str, Any]) -> dict[str, Any]:
        self._ensure_available()
        async with self._session_factory() as session:  # type: ignore[misc]
            record = await AgentSchedulerRepository(session).mark_completed(job_id, result)
            if record is None:
                raise ValueError(f"Scheduled job not found: {job_id}")
            return self._to_dict(record)

    async def _mark_failed(self, job_id: str, error: str) -> dict[str, Any]:
        self._ensure_available()
        async with self._session_factory() as session:  # type: ignore[misc]
            record = await AgentSchedulerRepository(session).mark_failed(job_id, error)
            if record is None:
                raise ValueError(f"Scheduled job not found: {job_id}")
            return self._to_dict(record)

    def _ensure_available(self) -> None:
        if self._session_factory is None:
            raise RuntimeError("Scheduler requires a configured database engine")

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @staticmethod
    def _to_dict(record: AgentScheduledJobRecord) -> dict[str, Any]:
        return {
            "job_id": record.job_id,
            "agent_id": record.agent_id,
            "session_id": record.session_id,
            "user_id": record.user_id,
            "job_type": record.job_type,
            "prompt": record.prompt,
            "run_at": record.run_at,
            "status": record.status,
            "result": record.result,
            "error": record.error,
            "metadata": record.metadata_json or {},
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
