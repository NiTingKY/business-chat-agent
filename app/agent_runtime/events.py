from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


AgentEventType = Literal[
    "turn.started",
    "memory.loaded",
    "message.persisted",
    "model.call",
    "model.error",
    "tool.called",
    "tool.result",
    "plan.created",
    "plan.step.created",
    "plan.step.started",
    "plan.step.completed",
    "plan.step.skipped",
    "plan.step.failed",
    "plan.completed",
    "memory.persisted",
    "agent.completed",
    "agent.stream.completed",
    "turn.failed",
]


@dataclass(slots=True)
class AgentEvent:
    type: AgentEventType
    turn_id: str
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class EventRecorder:
    """In-memory event recorder for the current process.

    This is intentionally small for Phase 1. Later phases can replace it with
    an audit-log backend without changing runtime call sites.
    """

    def __init__(self) -> None:
        self._events: list[AgentEvent] = []

    def record(self, event: AgentEvent) -> None:
        self._events.append(event)

    def list_events(self, *, turn_id: str | None = None) -> list[AgentEvent]:
        if turn_id is None:
            return list(self._events)
        return [event for event in self._events if event.turn_id == turn_id]
