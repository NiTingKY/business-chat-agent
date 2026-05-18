from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4

from app.domain.travel.itinerary import build_draft_itinerary, summarize_itinerary_text
from app.domain.travel.models import EmployeeGrade, TravelClass, TravelRequest, TripPurpose
from app.domain.travel.policy import apply_policy_to_itinerary, default_corporate_policy
from app.services.embeddings import EmbeddingService
from app.tools.base import AgentTool
from app.tools.registry import AgentToolRegistry

_policy_document_store: Any | None = None
_policy_embed_text: Any | None = None


def set_policy_document_store(store: Any | None, *, embed_text: Any | None = None) -> None:
    global _policy_document_store, _policy_embed_text
    _policy_document_store = store
    _policy_embed_text = embed_text


async def _search_policy_evidence(arguments: Mapping[str, Any]) -> list[dict[str, Any]]:
    if _policy_document_store is None or not getattr(_policy_document_store, "connected", False):
        return []
    grade_label = {
        "staff": "其余人员",
        "manager": "厅级及相当职级人员 高级专业技术职称人员",
        "director": "厅级及相当职级人员 高级专业技术职称人员",
        "executive": "省级及相当职级人员",
    }.get(str(arguments.get("grade") or ""), str(arguments.get("grade") or ""))
    query = " ".join(
        str(arguments.get(key) or "")
        for key in (
            "origin_city",
            "destination_city",
            "departure_date",
            "estimated_total_cny",
            "preferred_class",
        )
    ).strip()
    embed_text = _policy_embed_text or EmbeddingService().embed_text
    queries = [
        f"{grade_label} {query} 住宿费限额标准",
        "省外 伙食补助费 每人每天100元 公杂费 每人每天80元",
        "报销 住宿费发票 伙食补助费 公杂费 审批",
    ]
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for evidence_query in queries:
        vector = await embed_text(evidence_query)
        try:
            rows = list(_policy_document_store.search(vector, top_k=3, query=evidence_query))
        except TypeError:
            rows = list(_policy_document_store.search(vector, top_k=3))
        except Exception:
            rows = []
        for row in rows:
            key = str(row.get("id") or row.get("content") or "")
            if key in seen:
                continue
            seen.add(key)
            hits.append(row)
    return hits[:6]


def _format_policy_evidence(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return ""
    lines = ["", "向量库政策依据："]
    for index, hit in enumerate(hits, start=1):
        title = hit.get("title") or hit.get("id") or f"policy-{index}"
        content = str(hit.get("content") or "").strip()
        if len(content) > 700:
            content = content[:700].rstrip() + "..."
        lines.append(f"- [{title}] {content}")
    return "\n".join(lines)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _validate_future_dates(departure: date, return_date: date | None = None) -> str | None:
    today = date.today()
    if departure < today:
        return (
            f"工具参数错误：模型生成的 departure_date={departure.isoformat()} 早于今天 "
            f"{today.isoformat()}。如果最新用户消息没有明确给出这个日期，不要声称用户提供了该日期；"
            "请直接向用户询问有效的未来出发日期。"
        )
    if return_date and return_date < departure:
        return "工具参数错误：return_date 早于 departure_date。请向用户确认返程日期。"
    return None


PLAN_TRAVEL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "employee_id": {"type": "string"},
        "grade": {"type": "string", "enum": [g.value for g in EmployeeGrade]},
        "origin_city": {"type": "string"},
        "destination_city": {"type": "string"},
        "departure_date": {
            "type": "string",
            "description": "YYYY-MM-DD，必须是今天或未来日期",
        },
        "return_date": {
            "type": "string",
            "description": "YYYY-MM-DD，可选，必须不早于 departure_date",
        },
        "purpose": {"type": "string", "enum": [p.value for p in TripPurpose]},
        "preferred_class": {"type": "string", "enum": [c.value for c in TravelClass]},
    },
    "required": [
        "employee_id",
        "grade",
        "origin_city",
        "destination_city",
        "departure_date",
        "purpose",
    ],
}


CHECK_POLICY_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "employee_id": {"type": "string"},
        "grade": {"type": "string", "enum": [g.value for g in EmployeeGrade]},
        "origin_city": {"type": "string"},
        "destination_city": {"type": "string"},
        "departure_date": {
            "type": "string",
            "description": "YYYY-MM-DD，必须是今天或未来日期",
        },
        "return_date": {"type": "string"},
        "estimated_total_cny": {"type": "number"},
        "preferred_class": {"type": "string", "enum": [c.value for c in TravelClass]},
    },
    "required": [
        "employee_id",
        "grade",
        "origin_city",
        "destination_city",
        "departure_date",
        "estimated_total_cny",
    ],
}


async def plan_travel_itinerary(arguments: Mapping[str, Any]) -> str:
    policy = default_corporate_policy()
    departure = _parse_date(str(arguments["departure_date"]))
    return_date = _parse_date(str(arguments["return_date"])) if arguments.get("return_date") else None
    validation_error = _validate_future_dates(departure, return_date)
    if validation_error:
        return validation_error

    request = TravelRequest(
        request_id=str(uuid4()),
        employee_id=str(arguments["employee_id"]),
        grade=EmployeeGrade(str(arguments["grade"])),
        origin_city=str(arguments["origin_city"]),
        destination_city=str(arguments["destination_city"]),
        departure_date=departure,
        return_date=return_date,
        purpose=TripPurpose(str(arguments["purpose"])),
        preferred_class=TravelClass(str(arguments["preferred_class"]))
        if arguments.get("preferred_class")
        else None,
    )
    itinerary = build_draft_itinerary(request)
    itinerary = apply_policy_to_itinerary(
        policy,
        request,
        itinerary,
        preferred_class=request.preferred_class,
    )
    return summarize_itinerary_text(itinerary)


async def check_travel_policy(arguments: Mapping[str, Any]) -> str:
    policy = default_corporate_policy()
    departure = _parse_date(str(arguments["departure_date"]))
    return_date = _parse_date(str(arguments["return_date"])) if arguments.get("return_date") else None
    validation_error = _validate_future_dates(departure, return_date)
    if validation_error:
        return validation_error

    request = TravelRequest(
        request_id=str(uuid4()),
        employee_id=str(arguments["employee_id"]),
        grade=EmployeeGrade(str(arguments["grade"])),
        origin_city=str(arguments["origin_city"]),
        destination_city=str(arguments["destination_city"]),
        departure_date=departure,
        return_date=return_date,
        purpose=TripPurpose.CLIENT,
    )
    dummy = build_draft_itinerary(request)
    dummy = dummy.model_copy(
        update={"total_estimated_cny": Decimal(str(arguments["estimated_total_cny"]))}
    )
    preferred = (
        TravelClass(str(arguments["preferred_class"])) if arguments.get("preferred_class") else None
    )
    checked = apply_policy_to_itinerary(policy, request, dummy, preferred_class=preferred)
    hits = await _search_policy_evidence(arguments)
    base_result = "差标校验结果：\n" + "\n".join(
        f"- {warning}" for warning in checked.policy_warnings
    )
    return base_result + _format_policy_evidence(hits)


def build_travel_tools() -> list[AgentTool]:
    return [
        AgentTool(
            name="plan_travel_itinerary",
            description=(
                "根据结构化差旅需求生成草稿行程与费用预估。"
                "只有在用户提供明确出发日期时才调用；不得自行编造日期。"
            ),
            parameters=PLAN_TRAVEL_PARAMETERS,
            handler=plan_travel_itinerary,
            tags={"travel", "planning"},
        ),
        AgentTool(
            name="check_travel_policy",
            description=(
                "对已有行程草稿执行差标校验，包括舱位、预算、提前预订、审批线。"
                "日期必须来自用户或已有行程，不得自行编造。"
            ),
            parameters=CHECK_POLICY_PARAMETERS,
            handler=check_travel_policy,
            tags={"travel", "policy"},
        ),
    ]


def default_travel_tool_registry() -> AgentToolRegistry:
    return AgentToolRegistry(build_travel_tools())
