from __future__ import annotations

from app.core.memory.agent_memory import AgentMemoryManager
from app.domain.schemas import ChatMessage, MessageRole


def test_agent_memory_extracts_and_injects_relevant_user_preferences() -> None:
    manager = AgentMemoryManager(summary_turn_threshold=99)
    session_id = "memory-session"

    manager.observe_interaction(
        session_id=session_id,
        user_message=ChatMessage(role=MessageRole.USER, content="我的职级是经理，我喜欢高铁优先。"),
        assistant_content="已记录。",
    )

    context = manager.build_context(
        [ChatMessage(role=MessageRole.USER, content="下次去上海怎么安排？")],
        session_id=session_id,
        user_id="u001",
    )

    assert context.messages[0].role is MessageRole.SYSTEM
    assert "[Agent Memory]" in context.messages[0].content
    assert "我的职级是经理" in context.messages[0].content


def test_agent_memory_rolls_older_turns_into_summary() -> None:
    manager = AgentMemoryManager(summary_turn_threshold=4)
    session_id = "summary-session"

    for i in range(4):
        manager.observe_interaction(
            session_id=session_id,
            user_message=ChatMessage(role=MessageRole.USER, content=f"第 {i} 次出差从北京去上海。"),
            assistant_content=f"第 {i} 次回复。",
        )

    context = manager.build_context(
        [ChatMessage(role=MessageRole.USER, content="继续规划。")],
        session_id=session_id,
    )

    assert context.summary
    assert "用户曾提到" in context.messages[0].content


def test_agent_memory_does_not_hydrate_current_user_twice() -> None:
    manager = AgentMemoryManager(summary_turn_threshold=99)
    session_id = "no-dup-session"

    context = manager.build_context(
        [ChatMessage(role=MessageRole.USER, content="我的职级是经理。")],
        session_id=session_id,
    )
    manager.observe_interaction(
        session_id=session_id,
        user_message=ChatMessage(role=MessageRole.USER, content="我的职级是经理。"),
        assistant_content="已记录。",
    )
    next_context = manager.build_context(
        [ChatMessage(role=MessageRole.USER, content="继续。")],
        session_id=session_id,
    )

    hydrated_user_turns = [
        msg.content for msg in next_context.messages if msg.role is MessageRole.USER
    ]
    assert hydrated_user_turns.count("我的职级是经理。") == 1
