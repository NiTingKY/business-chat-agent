from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

import pytest

from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.session import AgentSession
from app.domain.schemas import ChatMessage, ChatRequest, MessageRole, StreamChunk, StreamChunkType
from app.gateway.api import ApiGateway


class FakeSessions:
    def __init__(self) -> None:
        self.saved: list[tuple[str | None, str | None, str, str]] = []
        self.history = [
            ChatMessage(role=MessageRole.USER, content="我的职级是经理。"),
            ChatMessage(role=MessageRole.ASSISTANT, content="已记录。"),
        ]

    async def load(self, session_id: str | None, user_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id or "", user_id=user_id, history=list(self.history))

    async def save_message(
        self,
        *,
        session_id: str | None,
        user_id: str | None,
        role: MessageRole | str,
        content: str,
    ) -> None:
        role_value = role.value if isinstance(role, MessageRole) else role
        self.saved.append((session_id, user_id, role_value, content))


class FakeOrchestrator:
    def __init__(self) -> None:
        self.received: list[ChatMessage] = []

    async def run_completion(
        self,
        messages: list[ChatMessage],
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        self.received = list(messages)
        return {
            "id": str(uuid.uuid4()),
            "created": int(time.time()),
            "model": "fake-agent",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "运行时回答"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def stream_completion(
        self,
        messages: list[ChatMessage],
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.received = list(messages)
        yield StreamChunk(type=StreamChunkType.CONTENT, index=0, delta="流")
        yield StreamChunk(type=StreamChunkType.CONTENT, index=1, delta="式")
        yield StreamChunk(type=StreamChunkType.DONE, index=2, finish_reason="stop")


@pytest.mark.asyncio
async def test_gateway_runs_chat_through_runtime_with_history() -> None:
    sessions = FakeSessions()
    orchestrator = FakeOrchestrator()
    runtime = AgentRuntime(
        agent_id="travel-agent",
        orchestrator=orchestrator,  # type: ignore[arg-type]
        sessions=sessions,  # type: ignore[arg-type]
    )
    gateway = ApiGateway(runtime)

    result = await gateway.complete_chat(
        ChatRequest(
            session_id="s1",
            user_id="u1",
            messages=[ChatMessage(role=MessageRole.USER, content="帮我规划上海出差。")],
        )
    )

    assert result.raw_response["model"] == "fake-agent"
    assert orchestrator.received[0].content == "我的职级是经理。"
    assert orchestrator.received[-1].content == "帮我规划上海出差。"
    assert ("s1", "u1", "user", "帮我规划上海出差。") in sessions.saved
    assert ("s1", "u1", "assistant", "运行时回答") in sessions.saved
    assert any(event["type"] == "memory.loaded" for event in result.events)


@pytest.mark.asyncio
async def test_gateway_stream_persists_full_assistant_reply() -> None:
    sessions = FakeSessions()
    runtime = AgentRuntime(
        agent_id="travel-agent",
        orchestrator=FakeOrchestrator(),  # type: ignore[arg-type]
        sessions=sessions,  # type: ignore[arg-type]
    )
    gateway = ApiGateway(runtime)

    chunks = [
        chunk
        async for chunk in gateway.stream_chat(
            ChatRequest(
                session_id="s2",
                user_id="u2",
                stream=True,
                messages=[ChatMessage(role=MessageRole.USER, content="流式测试")],
            )
        )
    ]

    assert chunks[-1].type is StreamChunkType.DONE
    assert ("s2", "u2", "assistant", "流式") in sessions.saved
