from __future__ import annotations

from collections.abc import AsyncIterator

from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.turn import AgentTurnContext, AgentTurnResult
from app.domain.schemas import ChatRequest, StreamChunk
from app.gateway.message import MessageEnvelope


class ApiGateway:
    """HTTP channel adapter for chat requests."""

    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    def envelope_from_chat(self, body: ChatRequest) -> MessageEnvelope:
        return MessageEnvelope(
            messages=body.messages,
            session_id=body.session_id,
            user_id=body.user_id,
            stream=body.stream,
            agent_id=self._runtime.agent_id,
            channel="api",
            locale=body.locale,
        )

    async def complete_chat(self, body: ChatRequest) -> AgentTurnResult:
        envelope = self.envelope_from_chat(body)
        return await self._runtime.run_turn(self._turn_context(envelope))

    async def stream_chat(self, body: ChatRequest) -> AsyncIterator[StreamChunk]:
        envelope = self.envelope_from_chat(body)
        async for chunk in self._runtime.stream_turn(self._turn_context(envelope)):
            yield chunk

    @staticmethod
    def _turn_context(envelope: MessageEnvelope) -> AgentTurnContext:
        return AgentTurnContext(
            agent_id=envelope.agent_id,
            session_id=envelope.session_id,
            user_id=envelope.user_id,
            messages=envelope.messages,
            channel=envelope.channel,
            locale=envelope.locale,
            metadata={"envelope_id": envelope.envelope_id, **envelope.metadata},
        )
