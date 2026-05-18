from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.schemas import ChatMessage, MessageRole
from app.infrastructure.database.repository import ChatRepository
from app.infrastructure.database.session import create_session_factory


@dataclass(slots=True)
class AgentSession:
    session_id: str
    user_id: str | None
    history: list[ChatMessage]


class AgentSessionManager:
    """Loads and persists per-session conversation state."""

    def __init__(self, db_engine: AsyncEngine | None = None, *, history_limit: int = 80) -> None:
        self._db_engine = db_engine
        self._history_limit = history_limit

    async def load(self, session_id: str | None, user_id: str | None = None) -> AgentSession:
        if not session_id:
            return AgentSession(session_id="", user_id=user_id, history=[])
        history = await self.load_history(session_id)
        return AgentSession(session_id=session_id, user_id=user_id, history=history)

    async def load_history(self, session_id: str | None) -> list[ChatMessage]:
        if not self._db_engine or not session_id:
            return []
        try:
            factory = create_session_factory(self._db_engine)
            async with factory() as session:
                repo = ChatRepository(session)
                rows = await repo.get_history(session_id=session_id, limit=self._history_limit)
        except Exception:
            return []

        messages: list[ChatMessage] = []
        for row in rows:
            try:
                messages.append(ChatMessage(role=MessageRole(row.role), content=row.content or ""))
            except ValueError:
                continue
        return messages

    async def save_message(
        self,
        *,
        session_id: str | None,
        user_id: str | None,
        role: MessageRole | str,
        content: str,
    ) -> None:
        if not self._db_engine or not session_id:
            return
        role_value = role.value if isinstance(role, MessageRole) else role
        try:
            factory = create_session_factory(self._db_engine)
            async with factory() as session:
                repo = ChatRepository(session)
                await repo.save_message(
                    session_id=session_id,
                    user_id=user_id or "anonymous",
                    role=role_value,
                    content=content,
                )
        except Exception:
            return

