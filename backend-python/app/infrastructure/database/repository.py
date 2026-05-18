from datetime import datetime
from typing import Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.database.models import (
    AgentAuditEventRecord,
    AgentMemoryRecord,
    AgentPlanRunRecord,
    AgentPlanStepRecord,
    AgentScheduledJobRecord,
    ChatHistory,
)

class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_message(self, session_id: str, user_id: str, role: str, content: str, tool_calls: Any = None) -> ChatHistory:
        msg = ChatHistory(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            tool_calls=tool_calls
        )
        self.session.add(msg)
        await self.session.commit()
        return msg

    async def get_history(self, session_id: str, limit: int = 50) -> List[ChatHistory]:
        stmt = select(ChatHistory).where(ChatHistory.session_id == session_id).order_by(ChatHistory.created_at.asc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentMemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_memory(
        self,
        *,
        agent_id: str,
        session_id: str,
        user_id: str | None,
        text: str,
        source: str = "heuristic",
        importance: float = 0.6,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMemoryRecord:
        existing = await self.session.execute(
            select(AgentMemoryRecord).where(
                AgentMemoryRecord.agent_id == agent_id,
                AgentMemoryRecord.session_id == session_id,
                AgentMemoryRecord.user_id == user_id,
                AgentMemoryRecord.text == text,
            )
        )
        record = existing.scalars().first()
        if record is None:
            record = AgentMemoryRecord(
                agent_id=agent_id,
                session_id=session_id,
                user_id=user_id,
                text=text,
                source=source,
                importance=importance,
                metadata_json=metadata or {},
            )
            self.session.add(record)
        else:
            record.source = source
            record.importance = importance
            record.metadata_json = metadata or {}
        await self.session.commit()
        return record

    async def list_memories(
        self,
        *,
        agent_id: str,
        session_id: str,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[AgentMemoryRecord]:
        stmt = (
            select(AgentMemoryRecord)
            .where(
                AgentMemoryRecord.agent_id == agent_id,
                AgentMemoryRecord.session_id == session_id,
            )
            .order_by(AgentMemoryRecord.importance.desc(), AgentMemoryRecord.updated_at.desc())
            .limit(limit)
        )
        if user_id:
            stmt = stmt.where(AgentMemoryRecord.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentAuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_event(
        self,
        *,
        event_id: str,
        turn_id: str,
        agent_id: str,
        session_id: str | None,
        user_id: str | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> AgentAuditEventRecord:
        existing = await self.session.execute(
            select(AgentAuditEventRecord).where(AgentAuditEventRecord.event_id == event_id)
        )
        record = existing.scalars().first()
        if record is None:
            record = AgentAuditEventRecord(
                event_id=event_id,
                turn_id=turn_id,
                agent_id=agent_id,
                session_id=session_id,
                user_id=user_id,
                event_type=event_type,
                payload=payload or {},
            )
            self.session.add(record)
            await self.session.commit()
        return record

    async def list_events(
        self,
        *,
        turn_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[AgentAuditEventRecord]:
        stmt = select(AgentAuditEventRecord).order_by(AgentAuditEventRecord.id.desc()).limit(limit)
        if turn_id:
            stmt = stmt.where(AgentAuditEventRecord.turn_id == turn_id)
        if session_id:
            stmt = stmt.where(AgentAuditEventRecord.session_id == session_id)
        if agent_id:
            stmt = stmt.where(AgentAuditEventRecord.agent_id == agent_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentSchedulerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_job(
        self,
        *,
        job_id: str,
        agent_id: str,
        session_id: str | None,
        user_id: str | None,
        job_type: str,
        prompt: str,
        run_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> AgentScheduledJobRecord:
        record = AgentScheduledJobRecord(
            job_id=job_id,
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            job_type=job_type,
            prompt=prompt,
            run_at=run_at,
            metadata_json=metadata or {},
            status="pending",
        )
        self.session.add(record)
        await self.session.commit()
        return record

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[AgentScheduledJobRecord]:
        stmt = select(AgentScheduledJobRecord).order_by(AgentScheduledJobRecord.run_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(AgentScheduledJobRecord.status == status)
        if session_id:
            stmt = stmt.where(AgentScheduledJobRecord.session_id == session_id)
        if agent_id:
            stmt = stmt.where(AgentScheduledJobRecord.agent_id == agent_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_due_jobs(
        self,
        *,
        now: datetime,
        limit: int = 20,
    ) -> list[AgentScheduledJobRecord]:
        stmt = (
            select(AgentScheduledJobRecord)
            .where(
                AgentScheduledJobRecord.status == "pending",
                AgentScheduledJobRecord.run_at <= now,
            )
            .order_by(AgentScheduledJobRecord.run_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_running(self, job_id: str) -> AgentScheduledJobRecord | None:
        record = await self._get_by_job_id(job_id)
        if record is None or record.status != "pending":
            return None
        record.status = "running"
        record.error = None
        await self.session.commit()
        return record

    async def mark_completed(self, job_id: str, result: dict[str, Any]) -> AgentScheduledJobRecord | None:
        record = await self._get_by_job_id(job_id)
        if record is None:
            return None
        record.status = "completed"
        record.result = result
        record.error = None
        await self.session.commit()
        return record

    async def mark_failed(self, job_id: str, error: str) -> AgentScheduledJobRecord | None:
        record = await self._get_by_job_id(job_id)
        if record is None:
            return None
        record.status = "failed"
        record.error = error
        await self.session.commit()
        return record

    async def _get_by_job_id(self, job_id: str) -> AgentScheduledJobRecord | None:
        result = await self.session.execute(
            select(AgentScheduledJobRecord).where(AgentScheduledJobRecord.job_id == job_id)
        )
        return result.scalars().first()


class AgentPlanRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_plan(
        self,
        *,
        plan_id: str,
        turn_id: str,
        agent_id: str,
        session_id: str | None,
        user_id: str | None,
        goal: str,
        steps: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> AgentPlanRunRecord:
        plan = AgentPlanRunRecord(
            plan_id=plan_id,
            turn_id=turn_id,
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            goal=goal,
            status="planned",
            metadata_json=metadata or {},
        )
        self.session.add(plan)
        for index, step in enumerate(steps, start=1):
            self.session.add(
                AgentPlanStepRecord(
                    step_id=step["step_id"],
                    plan_id=plan_id,
                    step_index=index,
                    title=step["title"],
                    description=step["description"],
                    suggested_tool=step.get("suggested_tool"),
                    status=step.get("status", "planned"),
                    output=step.get("output"),
                    error=step.get("error"),
                )
            )
        await self.session.commit()
        return plan

    async def list_plans(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AgentPlanRunRecord]:
        stmt = select(AgentPlanRunRecord).order_by(AgentPlanRunRecord.id.desc()).limit(limit)
        if session_id:
            stmt = stmt.where(AgentPlanRunRecord.session_id == session_id)
        if agent_id:
            stmt = stmt.where(AgentPlanRunRecord.agent_id == agent_id)
        if status:
            stmt = stmt.where(AgentPlanRunRecord.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_plan(self, plan_id: str) -> AgentPlanRunRecord | None:
        result = await self.session.execute(
            select(AgentPlanRunRecord).where(AgentPlanRunRecord.plan_id == plan_id)
        )
        return result.scalars().first()

    async def list_steps(self, plan_id: str) -> list[AgentPlanStepRecord]:
        result = await self.session.execute(
            select(AgentPlanStepRecord)
            .where(AgentPlanStepRecord.plan_id == plan_id)
            .order_by(AgentPlanStepRecord.step_index.asc())
        )
        return list(result.scalars().all())

    async def update_execution(
        self,
        *,
        plan_id: str,
        status: str,
        steps: list[dict[str, Any]],
    ) -> AgentPlanRunRecord | None:
        plan = await self.get_plan(plan_id)
        if plan is None:
            return None
        plan.status = status
        for step_data in steps:
            result = await self.session.execute(
                select(AgentPlanStepRecord).where(
                    AgentPlanStepRecord.step_id == step_data["step_id"]
                )
            )
            step = result.scalars().first()
            if step is None:
                continue
            step.status = step_data["status"]
            step.output = step_data.get("output")
            step.error = step_data.get("error")
        await self.session.commit()
        return plan
