from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.schemas import ChatMessage


@dataclass(slots=True)
class MessageEnvelope:
    messages: list[ChatMessage]
    session_id: str | None
    user_id: str | None
    stream: bool = False
    agent_id: str = "travel-agent"
    channel: str = "api"
    locale: str = "zh-CN"
    metadata: dict[str, Any] = field(default_factory=dict)
    envelope_id: str = field(default_factory=lambda: str(uuid.uuid4()))

