"""Agent-style memory inspired by LangChain memory primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from app.config import settings
from app.core.memory.short_term import ChatTurn, ShortTermMemory
from app.domain.schemas import ChatMessage, MessageRole


_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")


@dataclass(slots=True)
class SemanticMemory:
    text: str
    source: str
    importance: float = 0.6


@dataclass(slots=True)
class MemoryContext:
    messages: list[ChatMessage]
    recalled: list[SemanticMemory] = field(default_factory=list)
    summary: str | None = None


@dataclass
class SessionMemory:
    buffer: ShortTermMemory = field(
        default_factory=lambda: ShortTermMemory(
            max_turns=settings.memory_window_size,
            max_tokens=6000,
        )
    )
    summary: str = ""
    semantic: list[SemanticMemory] = field(default_factory=list)
    hydrated: bool = False


class AgentMemoryManager:
    """A lightweight MemoryManager similar to LangChain's combined memories."""

    def __init__(self, *, summary_turn_threshold: int | None = None) -> None:
        self._sessions: dict[str, SessionMemory] = {}
        self._summary_turn_threshold = summary_turn_threshold or settings.memory_summary_threshold

    def _session(self, session_id: str) -> SessionMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMemory()
        return self._sessions[session_id]

    def build_context(
        self,
        messages: list[ChatMessage],
        *,
        session_id: str | None,
        user_id: str | None = None,
    ) -> MemoryContext:
        if not session_id:
            return MemoryContext(messages=messages)

        session = self._session(session_id)
        if not session.hydrated:
            self._hydrate(session, self._history_without_current_user(messages))
            session.hydrated = True

        latest_user = self._latest_user_text(messages)
        recalled = self._recall(session, latest_user)
        memory_block = self._memory_block(
            session=session,
            recalled=recalled,
            session_id=session_id,
            user_id=user_id,
        )

        managed: list[ChatMessage] = []
        if memory_block:
            managed.append(ChatMessage(role=MessageRole.SYSTEM, content=memory_block))
        managed.extend(self._recent_messages(session, messages))
        return MemoryContext(messages=managed, recalled=recalled, summary=session.summary or None)

    def observe_interaction(
        self,
        *,
        session_id: str | None,
        user_message: ChatMessage | None,
        assistant_content: str,
    ) -> None:
        if not session_id or user_message is None:
            return
        session = self._session(session_id)
        session.buffer.append(ChatTurn(role="user", content=user_message.content))
        session.buffer.append(ChatTurn(role="assistant", content=assistant_content))
        for memory in self._extract_semantic_memories(user_message.content):
            self.add_semantic_memory(session_id, memory)
        self._maybe_roll_summary(session)

    def hydrate_semantic_memories(
        self,
        session_id: str | None,
        memories: Iterable[SemanticMemory],
    ) -> None:
        if not session_id:
            return
        for memory in memories:
            self.add_semantic_memory(session_id, memory)

    def add_semantic_memory(self, session_id: str, memory: SemanticMemory) -> None:
        session = self._session(session_id)
        if not self._has_semantic(session, memory.text):
            session.semantic.append(memory)

    def semantic_memories(self, session_id: str | None) -> list[SemanticMemory]:
        if not session_id:
            return []
        return list(self._session(session_id).semantic)

    def _hydrate(self, session: SessionMemory, messages: list[ChatMessage]) -> None:
        for msg in messages[-settings.memory_window_size :]:
            if msg.role in (MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM):
                role = "system" if msg.role is MessageRole.SYSTEM else msg.role.value
                session.buffer.append(ChatTurn(role=role, content=msg.content))
            if msg.role is MessageRole.USER:
                for memory in self._extract_semantic_memories(msg.content):
                    if not self._has_semantic(session, memory.text):
                        session.semantic.append(memory)
        older = messages[: -settings.memory_window_size]
        if older and not session.summary:
            session.summary = self._summarize_turns(older)

    def _recent_messages(
        self,
        session: SessionMemory,
        incoming: list[ChatMessage],
    ) -> list[ChatMessage]:
        turns = session.buffer.snapshot()
        recent = [
            ChatMessage(role=MessageRole(t.role), content=t.content)
            for t in turns
            if t.role in {"system", "user", "assistant"}
        ]
        latest = incoming[-1:] if incoming else []
        if latest and (not recent or recent[-1].content != latest[-1].content):
            recent.extend(latest)
        return recent[-settings.memory_window_size :]

    def _memory_block(
        self,
        *,
        session: SessionMemory,
        recalled: list[SemanticMemory],
        session_id: str,
        user_id: str | None,
    ) -> str:
        lines = ["[Agent Memory]", f"session_id: {session_id}"]
        if user_id:
            lines.append(f"user_id: {user_id}")
        if session.summary:
            lines.extend(["", "Rolling summary:", session.summary])
        if recalled:
            lines.append("")
            lines.append("Relevant long-term memories:")
            lines.extend(f"- {m.text}" for m in recalled)
        if not session.summary and not recalled:
            return ""
        lines.append("")
        lines.append("Use these memories as context, but prefer the latest user message when conflicts exist.")
        return "\n".join(lines)

    def _maybe_roll_summary(self, session: SessionMemory) -> None:
        turns = session.buffer.snapshot()
        if len(turns) <= self._summary_turn_threshold:
            return
        pivot = max(2, len(turns) - settings.memory_window_size)
        older = turns[:pivot]
        if not older:
            return
        new_summary = self._summarize_turns(
            ChatMessage(role=MessageRole(t.role), content=t.content) for t in older
        )
        session.summary = "\n".join(x for x in [session.summary, new_summary] if x).strip()
        session.buffer.clear()
        session.buffer.extend(turns[pivot:])

    def _summarize_turns(self, turns: Iterable[ChatMessage]) -> str:
        facts: list[str] = []
        for msg in turns:
            text = msg.content.strip()
            if not text:
                continue
            if msg.role is MessageRole.USER:
                facts.append(f"用户曾提到：{text[:120]}")
            elif msg.role is MessageRole.ASSISTANT:
                facts.append(f"助手曾回复：{text[:120]}")
            if len(facts) >= 8:
                break
        return "\n".join(f"- {x}" for x in facts)

    def _recall(self, session: SessionMemory, query: str, *, top_k: int = 5) -> list[SemanticMemory]:
        if not query or not session.semantic:
            return []
        q_tokens = set(_WORD_RE.findall(query.lower()))
        scored: list[tuple[float, SemanticMemory]] = []
        for memory in session.semantic:
            m_tokens = set(_WORD_RE.findall(memory.text.lower()))
            overlap = len(q_tokens & m_tokens)
            score = memory.importance + overlap * 0.25
            if overlap or memory.importance >= 0.8:
                scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [m for _, m in scored[:top_k]]

    @staticmethod
    def _latest_user_text(messages: list[ChatMessage]) -> str:
        return next((m.content for m in reversed(messages) if m.role is MessageRole.USER), "")

    @staticmethod
    def _history_without_current_user(messages: list[ChatMessage]) -> list[ChatMessage]:
        if messages and messages[-1].role is MessageRole.USER:
            return messages[:-1]
        return messages

    @staticmethod
    def _has_semantic(session: SessionMemory, text: str) -> bool:
        return any(m.text == text for m in session.semantic)

    @staticmethod
    def _extract_semantic_memories(text: str) -> list[SemanticMemory]:
        patterns = [
            r"(?:我|本人|用户)(?:是|为|属于)[^。！？\n]{2,40}",
            r"(?:我|本人|用户)(?:喜欢|偏好|倾向|希望|常坐|常住)[^。！？\n]{2,50}",
            r"(?:我的|本人)(?:职级|级别|岗位|部门|预算|出发地|常驻地)(?:是|为|:|：)?[^。！？\n]{2,50}",
            r"(?:以后|后续|下次)(?:都|请|帮我)?[^。！？\n]{2,60}",
        ]
        memories: list[SemanticMemory] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                value = match.group(0).strip()
                memories.append(SemanticMemory(text=value, source="heuristic", importance=0.85))
        return memories
