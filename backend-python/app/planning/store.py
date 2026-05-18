from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.database.models import AgentPlanRunRecord, AgentPlanStepRecord
from app.infrastructure.database.repository import AgentPlanRepository
from app.infrastructure.database.session import create_session_factory
from app.planning.models import PlanRun, PlanStep


class PersistentPlanStore:
    def __init__(self, engine: AsyncEngine | None):
        self._engine = engine
        self._session_factory = create_session_factory(engine) if engine is not None else None

    async def save_plan(self, plan: PlanRun) -> PlanRun | None:
        if self._session_factory is None:
            return None
        async with self._session_factory() as session:
            await AgentPlanRepository(session).create_plan(
                plan_id=plan.plan_id,
                turn_id=plan.turn_id,
                agent_id=plan.agent_id,
                session_id=plan.session_id,
                user_id=plan.user_id,
                goal=plan.goal,
                steps=[
                    {
                        "step_id": step.step_id,
                        "title": step.title,
                        "description": step.description,
                        "suggested_tool": step.suggested_tool,
                        "status": step.status,
                        "output": step.output,
                        "error": step.error,
                    }
                    for step in plan.steps
                ],
                metadata=plan.metadata,
            )
        return plan

    async def save_execution_result(self, plan: PlanRun) -> PlanRun | None:
        if self._session_factory is None:
            return None
        async with self._session_factory() as session:
            await AgentPlanRepository(session).update_execution(
                plan_id=plan.plan_id,
                status=plan.status,
                steps=[
                    {
                        "step_id": step.step_id,
                        "status": step.status,
                        "output": step.output,
                        "error": step.error,
                    }
                    for step in plan.steps
                ],
            )
        return plan

    async def list_plans(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[PlanRun]:
        if self._session_factory is None:
            return []
        async with self._session_factory() as session:
            repo = AgentPlanRepository(session)
            plans = await repo.list_plans(
                session_id=session_id,
                agent_id=agent_id,
                status=status,
                limit=limit,
            )
            return [await self._from_record(repo, record) for record in plans]

    async def get_plan(self, plan_id: str) -> PlanRun | None:
        if self._session_factory is None:
            return None
        async with self._session_factory() as session:
            repo = AgentPlanRepository(session)
            record = await repo.get_plan(plan_id)
            if record is None:
                return None
            return await self._from_record(repo, record)

    async def _from_record(self, repo: AgentPlanRepository, record: AgentPlanRunRecord) -> PlanRun:
        steps = await repo.list_steps(record.plan_id)
        return PlanRun(
            plan_id=record.plan_id,
            turn_id=record.turn_id,
            agent_id=record.agent_id,
            session_id=record.session_id,
            user_id=record.user_id,
            goal=record.goal,
            status=record.status,  # type: ignore[arg-type]
            steps=[self._step_from_record(step) for step in steps],
            metadata=record.metadata_json or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _step_from_record(record: AgentPlanStepRecord) -> PlanStep:
        return PlanStep(
            step_id=record.step_id,
            index=record.step_index,
            title=record.title,
            description=record.description,
            suggested_tool=record.suggested_tool,
            status=record.status,  # type: ignore[arg-type]
            output=record.output,
            error=record.error,
        )

    @staticmethod
    def to_public_dict(plan: PlanRun) -> dict[str, Any]:
        return plan.model_dump()
