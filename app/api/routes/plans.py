from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.planning.models import PlanListResponse, PlanRun

router = APIRouter(tags=["plans"])


@router.get("/plans/runs", response_model=PlanListResponse)
async def list_plan_runs(
    request: Request,
    session_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    store = getattr(request.app.state, "plan_store", None)
    if store is None:
        return {"plans": []}
    plans = await store.list_plans(
        session_id=session_id,
        agent_id=agent_id,
        status=status,
        limit=limit,
    )
    return {"plans": [plan.model_dump() for plan in plans]}


@router.get("/plans/runs/{plan_id}", response_model=PlanRun)
async def get_plan_run(request: Request, plan_id: str) -> dict:
    store = getattr(request.app.state, "plan_store", None)
    if store is None:
        raise HTTPException(status_code=404, detail="Plan store is not available")
    plan = await store.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan.model_dump()
