from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.config import settings
from app.scheduler.models import (
    ScheduledJobCreate,
    ScheduledJobListResponse,
    ScheduledJobRunResponse,
    ScheduledJobView,
)

router = APIRouter(tags=["scheduler"])


@router.post("/scheduler/jobs", response_model=ScheduledJobView)
async def create_scheduled_job(request: Request, body: ScheduledJobCreate) -> dict:
    scheduler = getattr(request.app.state, "scheduler_service", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler is not available")
    return await scheduler.create_job(
        agent_id=body.agent_id or settings.default_agent_id,
        session_id=body.session_id,
        user_id=body.user_id,
        prompt=body.prompt,
        run_at=body.run_at,
        job_type=body.job_type,
        metadata=body.metadata,
    )


@router.get("/scheduler/jobs", response_model=ScheduledJobListResponse)
async def list_scheduled_jobs(
    request: Request,
    status: str | None = Query(None),
    session_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    scheduler = getattr(request.app.state, "scheduler_service", None)
    if scheduler is None:
        return {"jobs": []}
    jobs = await scheduler.list_jobs(
        status=status,
        session_id=session_id,
        agent_id=agent_id,
        limit=limit,
    )
    return {"jobs": jobs}


@router.post("/scheduler/run-due", response_model=ScheduledJobRunResponse)
async def run_due_scheduled_jobs(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    scheduler = getattr(request.app.state, "scheduler_service", None)
    runtime = getattr(request.app.state, "agent_runtime", None)
    if scheduler is None or runtime is None:
        raise HTTPException(status_code=503, detail="Scheduler runtime is not available")
    jobs = await scheduler.run_due_once(runtime, limit=limit)
    return {"ran": len(jobs), "jobs": jobs}
