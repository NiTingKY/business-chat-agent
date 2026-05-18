from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.schemas import ChatMessage


@dataclass(slots=True)
class AgentTurnContext:
    agent_id: str
    session_id: str | None
    user_id: str | None
    messages: list[ChatMessage]
    channel: str = "api"
    locale: str = "zh-CN"
    metadata: dict[str, Any] = field(default_factory=dict)
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class AgentTurnResult:
    turn_id: str
    raw_response: dict[str, Any]
    session_id: str | None
    events: list[dict[str, Any]] = field(default_factory=list)

