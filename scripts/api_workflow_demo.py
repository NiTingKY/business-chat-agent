from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DB = ROOT / "travel_agent.db"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def dump(title: str, data: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def db_rows(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not db_path.exists():
        return [{"error": f"database not found: {db_path}"}]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


class DemoOrchestrator:
    async def run_completion(self, messages, *, session_id: str | None = None, user_id: str | None = None) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "created": int(time.time()),
            "model": "demo-orchestrator",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "演示回复：已读取计划图、工具执行结果和子 Agent 分派信息。",
                    },
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def stream_completion(self, messages, *, session_id: str | None = None, user_id: str | None = None):
        return
        yield

    def hydrate_semantic_memories(self, *, session_id: str | None, memories: list[Any]) -> None:
        return None

    def semantic_memories(self, session_id: str | None) -> list[Any]:
        from app.core.memory.agent_memory import SemanticMemory

        return [
            SemanticMemory(text="用户是经理", source="demo", importance=0.8),
            SemanticMemory(text="用户本次关注北京到上海出差差标和审批", source="demo", importance=0.7),
        ]


def post(client: Any, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


def get(client: Any, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.get(path, params=params, timeout=180)
    response.raise_for_status()
    return response.json()


def build_client(base_url: str, transport: str) -> Any:
    if transport == "server":
        return httpx.Client(base_url=base_url)

    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.agent_runtime._orchestrator = DemoOrchestrator()
    return client


def close_client(client: Any, transport: str) -> None:
    if transport == "server":
        client.close()
    else:
        client.__exit__(None, None, None)


def run_demo(base_url: str, db_path: Path, transport: str) -> None:
    session_id = f"api-demo-{uuid.uuid4()}"
    scheduler_session_id = f"scheduler-demo-{uuid.uuid4()}"
    user_id = "api-demo-user"

    chat_message = (
        "我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，"
        "预算3000元，检查差标和审批要求。"
    )

    client = build_client(base_url, transport)
    try:
        health = get(client, "/api/v1/health")
        dump("1. GET /api/v1/health", health)

        chat = post(
            client,
            "/api/v1/chat",
            {
                "session_id": session_id,
                "user_id": user_id,
                "messages": [{"role": "user", "content": chat_message}],
            },
        )
        dump(
            "2. POST /api/v1/chat",
            {
                "session_id": session_id,
                "assistant_reply": chat["choices"][0]["message"]["content"],
                "model": chat.get("model"),
            },
        )

        plans = get(client, "/api/v1/plans/runs", {"session_id": session_id, "limit": 5})
        dump(
            "3. GET /api/v1/plans/runs",
            {
                "plan_count": len(plans["plans"]),
                "plans": [
                    {
                        "plan_id": plan["plan_id"],
                        "status": plan["status"],
                        "steps": [
                            {
                                "index": step["index"],
                                "title": step["title"],
                                "tool": step["suggested_tool"],
                                "status": step["status"],
                                "agent_role": (step.get("output") or {}).get("agent_role"),
                                "assigned_agent": (step.get("output") or {}).get("assigned_agent"),
                            }
                            for step in plan["steps"]
                        ],
                    }
                    for plan in plans["plans"]
                ],
            },
        )

        audit = get(client, "/api/v1/audit/events", {"session_id": session_id, "limit": 30})
        dump(
            "4. GET /api/v1/audit/events",
            {
                "event_count": len(audit["events"]),
                "event_types": [event["event_type"] for event in audit["events"]],
            },
        )

        ingest = post(
            client,
            "/api/v1/documents/ingest",
            {
                "title": "经理级差旅政策测试文档",
                "content": (
                    "经理级员工国内出差可优先选择高铁二等座或经济舱。"
                    "超过3000元预算需要提前审批，酒店应符合当地差标。"
                ),
                "doc_type": "policy",
                "metadata": {"source": "api_workflow_demo"},
            },
        )
        dump("5. POST /api/v1/documents/ingest", ingest)

        search = get(
            client,
            "/api/v1/documents/search",
            {"q": "经理出差预算审批酒店差标", "top_k": 3},
        )
        dump(
            "6. GET /api/v1/documents/search",
            {
                "backend": search.get("backend"),
                "result_count": len(search.get("results") or []),
                "top_result": (search.get("results") or [{}])[0],
            },
        )

        scheduled = post(
            client,
            "/api/v1/scheduler/jobs",
            {
                "session_id": scheduler_session_id,
                "user_id": user_id,
                "prompt": "提醒我检查北京到上海出差审批是否完成。",
                "run_at": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
                "metadata": {"source": "api_workflow_demo"},
            },
        )
        dump(
            "7. POST /api/v1/scheduler/jobs",
            {
                "job_id": scheduled["job_id"],
                "status": scheduled["status"],
                "run_at": scheduled["run_at"],
                "session_id": scheduler_session_id,
            },
        )

        listed_jobs = get(client, "/api/v1/scheduler/jobs", {"session_id": scheduler_session_id})
        dump(
            "8. GET /api/v1/scheduler/jobs",
            {
                "job_count": len(listed_jobs["jobs"]),
                "jobs": [
                    {
                        "job_id": job["job_id"],
                        "status": job["status"],
                        "prompt": job["prompt"],
                    }
                    for job in listed_jobs["jobs"]
                ],
            },
        )
    finally:
        close_client(client, transport)

    # Let async commits fully settle before reading SQLite from another process.
    time.sleep(0.2)
    dump(
        "DB: chat_history",
        db_rows(
            db_path,
            """
            select id, session_id, user_id, role, substr(content, 1, 160) as content, created_at
            from chat_history
            where session_id = ?
            order by id asc
            """,
            (session_id,),
        ),
    )
    dump(
        "DB: agent_memories",
        db_rows(
            db_path,
            """
            select id, agent_id, session_id, user_id, text, source, importance, metadata_json
            from agent_memories
            where session_id = ?
            order by id asc
            """,
            (session_id,),
        ),
    )
    dump(
        "DB: agent_plan_runs",
        db_rows(
            db_path,
            """
            select id, plan_id, turn_id, agent_id, session_id, user_id, status, substr(goal, 1, 160) as goal
            from agent_plan_runs
            where session_id = ?
            order by id desc
            """,
            (session_id,),
        ),
    )
    dump(
        "DB: agent_plan_steps",
        db_rows(
            db_path,
            """
            select s.id, s.plan_id, s.step_index, s.title, s.suggested_tool, s.status,
                   substr(s.output, 1, 260) as output_preview, s.error
            from agent_plan_steps s
            join agent_plan_runs p on p.plan_id = s.plan_id
            where p.session_id = ?
            order by s.step_index asc
            """,
            (session_id,),
        ),
    )
    dump(
        "DB: agent_audit_events",
        db_rows(
            db_path,
            """
            select id, event_type, turn_id, agent_id, session_id, substr(payload, 1, 260) as payload_preview
            from agent_audit_events
            where session_id = ?
            order by id desc
            limit 30
            """,
            (session_id,),
        ),
    )
    dump(
        "DB: agent_scheduled_jobs",
        db_rows(
            db_path,
            """
            select id, job_id, agent_id, session_id, user_id, job_type, status, prompt, run_at, result, error
            from agent_scheduled_jobs
            where session_id = ?
            order by id desc
            """,
            (scheduler_session_id,),
        ),
    )

    print("\n=== Where to inspect manually ===")
    print(f"SQLite DB: {db_path}")
    print("Tables: chat_history, agent_memories, agent_plan_runs, agent_plan_steps, agent_audit_events, agent_scheduled_jobs")
    print("Document vectors: Milvus if available; otherwise in-memory vector store for the current server process.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run API workflow demo and verify DB writes.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument(
        "--transport",
        choices=["inprocess", "server"],
        default="inprocess",
        help=(
            "inprocess uses FastAPI TestClient and a demo orchestrator so it does not depend on an external LLM; "
            "server sends real HTTP requests to --base-url."
        ),
    )
    args = parser.parse_args()

    try:
        run_demo(args.base_url.rstrip("/"), Path(args.db), args.transport)
    except httpx.ConnectError:
        print(f"Cannot connect to {args.base_url}. Start the server first:", file=sys.stderr)
        print("  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
