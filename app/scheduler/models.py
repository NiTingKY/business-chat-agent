from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


JobStatus = Literal["pending", "running", "completed", "failed"]
JobType = Literal["agent_turn"]


class ScheduledJobCreate(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    run_at: datetime
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    job_type: JobType = "agent_turn"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_at")
    @classmethod
    def normalize_run_at(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class ScheduledJobView(BaseModel):
    job_id: str
    agent_id: str
    session_id: str | None
    user_id: str | None
    job_type: str
    prompt: str
    run_at: datetime
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScheduledJobListResponse(BaseModel):
    jobs: list[ScheduledJobView]


class ScheduledJobRunResponse(BaseModel):
    ran: int
    jobs: list[ScheduledJobView]
