from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict

from app.agent.orchestrator import TravelOrchestrator
from app.agent_runtime.agent_config import AgentConfig
from app.agent_runtime.audit import PersistentAuditStore
from app.agent_runtime.events import AgentEvent, EventRecorder
from app.agent_runtime.lifecycle import AgentLifecycle
from app.agent_runtime.session import AgentSessionManager
from app.agent_runtime.turn import AgentTurnContext, AgentTurnResult
from app.core.memory.persistent_store import PersistentAgentMemoryStore
from app.domain.schemas import ChatMessage, MessageRole, StreamChunk
from app.planning.executor import PlanStepExecutor
from app.planning.planner import HeuristicTravelPlanner
from app.planning.store import PersistentPlanStore


class AgentRuntime:
    """OpenClaw-style runtime boundary for one logical agent."""

    def __init__(
        self,
        *,
        agent_id: str,
        orchestrator: TravelOrchestrator,
        sessions: AgentSessionManager,
        config: AgentConfig | None = None,
        memory_store: PersistentAgentMemoryStore | None = None,
        audit_store: PersistentAuditStore | None = None,
        plan_store: PersistentPlanStore | None = None,
        planner: HeuristicTravelPlanner | None = None,
        plan_executor: PlanStepExecutor | None = None,
        lifecycle: AgentLifecycle | None = None,
        events: EventRecorder | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.config = config
        self._orchestrator = orchestrator
        self._sessions = sessions
        self._memory_store = memory_store
        self._audit_store = audit_store
        self._plan_store = plan_store
        self._planner = planner or HeuristicTravelPlanner()
        self._plan_executor = plan_executor
        self._lifecycle = lifecycle or AgentLifecycle()
        self._events = events or EventRecorder()
        self._lifecycle.initialize()
        self._lifecycle.start()

    @property
    def lifecycle(self) -> AgentLifecycle:
        return self._lifecycle

    @property
    def events(self) -> EventRecorder:
        return self._events

    async def run_turn(self, context: AgentTurnContext) -> AgentTurnResult:
        try:
            self._record_turn_started(context)
            final_messages = await self._build_turn_messages(context)
            final_messages = await self._maybe_create_plan(context, final_messages)
            await self._persist_inbound(context)
            raw = await self._orchestrator.run_completion(
                final_messages,
                session_id=context.session_id,
                user_id=context.user_id,
            )
            self._record_orchestrator_audit(context, raw)
            assistant_content = raw["choices"][0]["message"]["content"]
            await self._sessions.save_message(
                session_id=context.session_id,
                user_id=context.user_id,
                role=MessageRole.ASSISTANT,
                content=assistant_content,
            )
            await self._persist_semantic_memory(context)
            self._record("agent.completed", context, model=raw.get("model"))
            await self._persist_audit_events(context)
            return AgentTurnResult(
                turn_id=context.turn_id,
                raw_response=raw,
                session_id=context.session_id,
                events=[asdict(event) for event in self._events.list_events(turn_id=context.turn_id)],
            )
        except Exception as exc:
            self._lifecycle.fail()
            self._record("turn.failed", context, error=str(exc))
            await self._persist_audit_events(context)
            raise

    async def stream_turn(self, context: AgentTurnContext) -> AsyncIterator[StreamChunk]:
        full_reply = ""
        try:
            self._record_turn_started(context, stream=True)
            final_messages = await self._build_turn_messages(context)
            final_messages = await self._maybe_create_plan(context, final_messages)
            await self._persist_inbound(context)
            async for chunk in self._orchestrator.stream_completion(
                final_messages,
                session_id=context.session_id,
                user_id=context.user_id,
            ):
                if chunk.delta:
                    full_reply += chunk.delta
                yield chunk
            if full_reply:
                await self._sessions.save_message(
                    session_id=context.session_id,
                    user_id=context.user_id,
                    role=MessageRole.ASSISTANT,
                    content=full_reply,
                )
            await self._persist_semantic_memory(context)
            self._record("agent.stream.completed", context)
            await self._persist_audit_events(context)
        except Exception as exc:
            self._lifecycle.fail()
            self._record("turn.failed", context, error=str(exc))
            await self._persist_audit_events(context)
            raise

    async def _build_turn_messages(self, context: AgentTurnContext) -> list[ChatMessage]:
        session = await self._sessions.load(context.session_id, context.user_id)
        await self._hydrate_semantic_memory(context)
        self._record("memory.loaded", context, history_count=len(session.history))
        if len(context.messages) == 1 and session.history:
            return session.history + context.messages
        return context.messages

    async def _maybe_create_plan(
        self,
        context: AgentTurnContext,
        messages: list[ChatMessage],
    ) -> list[ChatMessage]:
        plan = self._planner.build_plan(
            turn_id=context.turn_id,
            agent_id=context.agent_id,
            session_id=context.session_id,
            user_id=context.user_id,
            messages=messages,
        )
        if plan is None:
            return messages
        if self._plan_store is not None:
            await self._plan_store.save_plan(plan)
        self._record(
            "plan.created",
            context,
            plan_id=plan.plan_id,
            goal=plan.goal,
            step_count=len(plan.steps),
        )
        for step in plan.steps:
            self._record(
                "plan.step.created",
                context,
                plan_id=plan.plan_id,
                step_id=step.step_id,
                step_index=step.index,
                title=step.title,
                suggested_tool=step.suggested_tool,
            )
        if self._plan_executor is not None:
            for step in plan.steps:
                self._record(
                    "plan.step.started",
                    context,
                    plan_id=plan.plan_id,
                    step_id=step.step_id,
                    step_index=step.index,
                    title=step.title,
                    suggested_tool=step.suggested_tool,
                )
            plan = await self._plan_executor.execute(plan)
            if self._plan_store is not None:
                await self._plan_store.save_execution_result(plan)
            for step in plan.steps:
                output = step.output if isinstance(step.output, dict) else {}
                self._record(
                    f"plan.step.{step.status}",
                    context,
                    plan_id=plan.plan_id,
                    step_id=step.step_id,
                    step_index=step.index,
                    title=step.title,
                    suggested_tool=step.suggested_tool,
                    assigned_agent=output.get("assigned_agent"),
                    agent_role=output.get("agent_role"),
                    error=step.error,
                    has_output=step.output is not None,
                )
            self._record("plan.completed", context, plan_id=plan.plan_id, status=plan.status)
        context.metadata["plan_id"] = plan.plan_id
        plan_content = self._planner.format_for_prompt(plan)
        if self._plan_executor is not None:
            plan_content = f"{plan_content}\n\n{self._plan_executor.format_execution_summary(plan)}"
        plan_message = ChatMessage(role=MessageRole.SYSTEM, content=plan_content)
        latest_user_index = next(
            (index for index in range(len(messages) - 1, -1, -1) if messages[index].role is MessageRole.USER),
            len(messages),
        )
        return [*messages[:latest_user_index], plan_message, *messages[latest_user_index:]]

    async def _hydrate_semantic_memory(self, context: AgentTurnContext) -> None:
        if not self._memory_store:
            return
        memories = await self._memory_store.load(
            agent_id=context.agent_id,
            session_id=context.session_id,
            user_id=context.user_id,
        )
        self._orchestrator.hydrate_semantic_memories(
            session_id=context.session_id,
            memories=memories,
        )
        self._record("memory.loaded", context, semantic_count=len(memories))

    async def _persist_semantic_memory(self, context: AgentTurnContext) -> None:
        if not self._memory_store:
            return
        memories = self._orchestrator.semantic_memories(context.session_id)
        await self._memory_store.save(
            agent_id=context.agent_id,
            session_id=context.session_id,
            user_id=context.user_id,
            memories=memories,
        )
        self._record("memory.persisted", context, semantic_count=len(memories))

    async def _persist_inbound(self, context: AgentTurnContext) -> None:
        for message in context.messages:
            if message.role is MessageRole.USER:
                await self._sessions.save_message(
                    session_id=context.session_id,
                    user_id=context.user_id,
                    role=message.role,
                    content=message.content,
                )
                self._record("message.persisted", context, role=message.role.value)

    def _record(self, event_type: str, context: AgentTurnContext, **payload: object) -> None:
        self._events.record(
            AgentEvent(
                type=event_type,  # type: ignore[arg-type]
                turn_id=context.turn_id,
                payload={
                    "agent_id": context.agent_id,
                    "session_id": context.session_id,
                    "user_id": context.user_id,
                    "channel": context.channel,
                    **payload,
                },
            )
        )

    def _record_turn_started(self, context: AgentTurnContext, **payload: object) -> None:
        config_payload: dict[str, object] = {}
        if self.config:
            config_payload = {
                "workspace_agent": self.config.agent_id,
                "model": self.config.model,
                "enabled_tools": list(self.config.enabled_tools),
                "enabled_skills": list(self.config.enabled_skills),
                "memory_backend": self.config.memory_backend,
                "vector_backend": self.config.vector_backend,
            }
        self._record(
            "turn.started",
            context,
            message_count=len(context.messages),
            metadata=dict(context.metadata),
            **config_payload,
            **payload,
        )

    def _record_orchestrator_audit(self, context: AgentTurnContext, raw: dict) -> None:
        for event in raw.get("_audit_events", []):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type") or "agent.completed")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            self._record(event_type, context, **payload)

    async def _persist_audit_events(self, context: AgentTurnContext) -> None:
        if not self._audit_store:
            return
        await self._audit_store.save_events(self._events.list_events(turn_id=context.turn_id))
