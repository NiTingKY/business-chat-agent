from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Optional

from app.config import settings
from app.core.memory.agent_memory import AgentMemoryManager
from app.domain.schemas import ChatMessage, MessageRole, StreamChunk, StreamChunkType
from app.services.llm import LLMService
from app.tools.registry import AgentToolRegistry
from app.tools.travel import default_travel_tool_registry

DEFAULT_SYSTEM_PROMPT = """你是企业差旅智能体“商旅-agent-guide”。
你帮助员工规划差旅行程、解释差标、估算费用和说明审批要求。

规则：
1. 涉及金额、差标、审批时必须说明“以公司制度为准”。
2. 不要编造出发日期。如果用户没有给出明确日期，应先追问或给出不绑定日期的建议。
3. 调用行程/差标工具时，departure_date 和 return_date 必须是今天或未来日期。
4. 用户偏好和历史记忆只作为辅助上下文；当它们与最新用户消息冲突时，以最新消息为准。
5. 回答应简洁、专业，并给出可执行的下一步。
"""
RUNTIME_POLICY_GUIDANCE = """
差旅政策解释规则：
1. 政策中的“其余人员”按系统工具参数 grade=staff 处理，不要要求用户改说 staff。
2. 政策中的“厅级及相当职级人员、高级专业技术职称人员”可按 manager/director 处理。
3. 政策中的“省级及相当职级人员”可按 executive 处理。
4. 如果 [Plan execution] 或工具结果已经给出差标、补助或向量库政策依据，最终回答必须优先使用这些证据，不要因为枚举字段名不同而拒答。
5. 北京、上海、海南、西藏、青海、深圳这一行的其余人员住宿费限额是 350 元/天；省外伙食补助费是 100 元/天（西藏、青海、新疆 120 元/天）；省外公杂费是 80 元/天。
"""


def _to_openai_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {"role": message.role.value, "content": message.content}
        if message.name:
            item["name"] = message.name
        if message.tool_call_id:
            item["tool_call_id"] = message.tool_call_id
        out.append(item)
    return out


class TravelOrchestrator:
    def __init__(
        self,
        llm: Optional[LLMService] = None,
        tool_registry: AgentToolRegistry | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._llm = llm or LLMService()
        self._memory = AgentMemoryManager()
        self._tools = tool_registry or default_travel_tool_registry()
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def _fallback_completion(
        self,
        messages: list[ChatMessage],
        reason: str | None = None,
    ) -> dict[str, Any]:
        last_user = next((m.content for m in reversed(messages) if m.role is MessageRole.USER), "")
        hint = ""
        if "北京" in last_user and "上海" in last_user:
            hint = (
                "\n\n示例建议：北京到上海一日差旅可优先比较高铁和航班。"
                "若偏好高铁，可选择早班高铁去、晚班高铁回；若时间敏感，再比较航班。"
            )
        content = (
            "当前外部大模型暂时不可用，我先按本地规则给出建议：\n"
            "1. 请确认出发地、目的地、出发/返回日期、员工职级和出差目的。\n"
            "2. 普通员工默认经济舱；经理可按制度申请高端经济舱；超审批线需提前走 OA。\n"
            "3. 如果日期未明确，我不会替你编造日期，建议先补充日期后再做差标校验。"
            f"{hint}"
        )
        if reason:
            content += f"\n\n技术提示：{reason}"
        return {
            "id": str(uuid.uuid4()),
            "created": int(time.time()),
            "model": f"{self._llm.model}:local-fallback",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    async def _maybe_summarize_thread(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if len(messages) <= settings.memory_summary_threshold:
            return messages
        head = messages[: -settings.memory_window_size]
        tail = messages[-settings.memory_window_size :]
        summary_req = [
            {
                "role": "system",
                "content": "将下面对话压缩为不超过 300 字的中文摘要，保留城市、日期、政策、金额和用户偏好。",
            },
            {"role": "user", "content": "\n".join(f"{m.role.value}: {m.content}" for m in head)},
        ]
        summary = await self._llm.chat_completion(summary_req, temperature=0.0)
        text = summary.choices[0].message.content or ""
        return [ChatMessage(role=MessageRole.SYSTEM, content=f"[历史摘要] {text}"), *tail]

    def _trim_window(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if len(messages) <= settings.memory_window_size:
            return messages
        return messages[-settings.memory_window_size :]

    async def _execute_tool(self, name: str, arguments: str) -> str:
        args: dict[str, Any] = json.loads(arguments) if arguments else {}
        try:
            return await self._tools.invoke(name, args)
        except Exception as exc:
            return json.dumps({"error": f"tool {name} failed: {exc}"}, ensure_ascii=False)

    async def run_completion(
        self,
        messages: list[ChatMessage],
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        audit_events: list[dict[str, Any]] = []
        memory_context = self._memory.build_context(
            messages,
            session_id=session_id,
            user_id=user_id,
        )
        audit_events.append(
            {
                "type": "memory.loaded",
                "payload": {
                    "recalled_count": len(memory_context.recalled),
                    "has_summary": memory_context.summary is not None,
                },
            }
        )
        try:
            msgs = await self._maybe_summarize_thread(memory_context.messages)
        except Exception:
            msgs = self._trim_window(memory_context.messages)
        msgs = self._trim_window(msgs)
        openai_msgs: list[dict[str, Any]] = [
            {"role": "system", "content": f"{self._system_prompt}\n\n{RUNTIME_POLICY_GUIDANCE}"}
        ]
        openai_msgs.extend(_to_openai_messages(msgs))

        tools = self._tools.openai_tools()
        for iteration in range(settings.max_react_iterations):
            try:
                audit_events.append(
                    {
                        "type": "model.call",
                        "payload": {
                            "iteration": iteration,
                            "model": self._llm.model,
                            "message_count": len(openai_msgs),
                            "tool_count": len(tools),
                        },
                    }
                )
                resp = await self._llm.chat_completion(openai_msgs, tools=tools, tool_choice="auto")
            except Exception as exc:
                audit_events.append(
                    {
                        "type": "model.error",
                        "payload": {"iteration": iteration, "error": str(exc)},
                    }
                )
                raw = self._fallback_completion(messages, str(exc))
                raw["_audit_events"] = audit_events
                self._record_memory(session_id, messages, raw)
                return raw
            choice = resp.choices[0]
            msg = choice.message

            if msg.tool_calls:
                openai_msgs.append(
                    {
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments or "{}",
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
                for tc in msg.tool_calls:
                    audit_events.append(
                        {
                            "type": "tool.called",
                            "payload": {
                                "tool_name": tc.function.name,
                                "tool_call_id": tc.id,
                                "arguments": tc.function.arguments or "{}",
                            },
                        }
                    )
                    out = await self._execute_tool(tc.function.name, tc.function.arguments)
                    audit_events.append(
                        {
                            "type": "tool.result",
                            "payload": {
                                "tool_name": tc.function.name,
                                "tool_call_id": tc.id,
                                "result_preview": out[:500],
                            },
                        }
                    )
                    openai_msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": out,
                        }
                    )
                continue

            raw = {
                "id": getattr(resp, "id", str(uuid.uuid4())),
                "created": int(time.time()),
                "model": self._llm.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": msg.content or ""},
                    }
                ],
                "usage": {
                    "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                    "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
                    "total_tokens": resp.usage.total_tokens if resp.usage else 0,
                },
            }
            raw["_audit_events"] = audit_events
            self._record_memory(session_id, messages, raw)
            return raw

        raw = {
            "id": str(uuid.uuid4()),
            "created": int(time.time()),
            "model": self._llm.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "已达到最大推理轮次，请简化问题后重试。",
                    },
                }
            ],
            "usage": None,
        }
        raw["_audit_events"] = audit_events
        self._record_memory(session_id, messages, raw)
        return raw

    def _record_memory(
        self,
        session_id: str | None,
        messages: list[ChatMessage],
        raw: dict[str, Any],
    ) -> None:
        latest_user = next((m for m in reversed(messages) if m.role is MessageRole.USER), None)
        assistant_content = raw["choices"][0]["message"]["content"]
        self._memory.observe_interaction(
            session_id=session_id,
            user_message=latest_user,
            assistant_content=assistant_content,
        )

    def hydrate_semantic_memories(
        self,
        *,
        session_id: str | None,
        memories: list[Any],
    ) -> None:
        self._memory.hydrate_semantic_memories(session_id, memories)

    def semantic_memories(self, session_id: str | None) -> list[Any]:
        return self._memory.semantic_memories(session_id)

    async def stream_completion(
        self,
        messages: list[ChatMessage],
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        result = await self.run_completion(messages, session_id=session_id, user_id=user_id)
        text = result["choices"][0]["message"]["content"]
        for i, ch in enumerate(text):
            yield StreamChunk(type=StreamChunkType.CONTENT, index=i, delta=ch)
        yield StreamChunk(type=StreamChunkType.DONE, index=len(text), finish_reason="stop")
