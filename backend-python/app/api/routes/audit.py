from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter(tags=["audit"])


@router.get("/audit/events")
async def list_audit_events(
    request: Request,
    turn_id: str | None = Query(None),
    session_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    audit_store = getattr(request.app.state, "audit_store", None)
    if audit_store is None:
        return {"events": []}
    events = await audit_store.list_events(
        turn_id=turn_id,
        session_id=session_id,
        agent_id=agent_id,
        limit=limit,
    )
    return {"events": events}
