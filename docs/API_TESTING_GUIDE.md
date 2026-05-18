# API Testing Guide

本文件给出 Swagger 文档中主要接口的请求代码，以及请求后可以在哪里看到落库数据。

默认服务地址：

```text
http://127.0.0.1:8000
```

默认 SQLite 数据库：

```text
D:\java\travel-agent-guide-main\project-python\travel_agent.db
```

一键演示脚本：

```powershell
D:\miniconda\envs\stbp\python.exe scripts\api_workflow_demo.py
```

它会依次请求 health、chat、plans、audit、documents、scheduler，并在最后查询 SQLite 表。默认使用 `inprocess` 模式，也就是通过 FastAPI TestClient 调用同一套 API 路由，并替换一个演示 orchestrator，避免外部大模型超时影响测试。

如果你要测试当前浏览器里 `http://127.0.0.1:8000/docs` 对应的真实服务，可以运行：

```powershell
D:\miniconda\envs\stbp\python.exe scripts\api_workflow_demo.py --transport server
```

注意：`--transport server` 会使用真实模型配置，模型网关慢或失败时 `/api/v1/chat` 可能等待较久或走 fallback。

## 1. Health

请求代码：

```python
import httpx

resp = httpx.get("http://127.0.0.1:8000/api/v1/health")
print(resp.json())
```

说明：

- 不落业务表。
- 用来确认 Redis、数据库、向量库是否可用。

## 2. Chat

请求代码：

```python
import httpx

session_id = "demo-session-001"
payload = {
    "session_id": session_id,
    "user_id": "demo-user",
    "messages": [
        {
            "role": "user",
            "content": "我是经理，帮我规划北京到上海的出差行程，出发日期是2026-06-01，预算3000元，检查差标和审批要求。"
        }
    ]
}

resp = httpx.post("http://127.0.0.1:8000/api/v1/chat", json=payload, timeout=90)
print(resp.json())
```

会落库：

```text
chat_history
agent_memories
agent_plan_runs
agent_plan_steps
agent_audit_events
```

查看 SQL：

```sql
select * from chat_history where session_id = 'demo-session-001';
select * from agent_memories where session_id = 'demo-session-001';
select * from agent_plan_runs where session_id = 'demo-session-001';
select s.* from agent_plan_steps s join agent_plan_runs p on p.plan_id = s.plan_id where p.session_id = 'demo-session-001';
select * from agent_audit_events where session_id = 'demo-session-001' order by id desc;
```

你应该能看到：

- `chat_history` 中有 user 和 assistant 消息。
- `agent_plan_runs` 中有一条 `completed` 计划。
- `agent_plan_steps` 中有 `check_travel_policy`、`plan_travel_itinerary` 两个工具步骤。
- `agent_plan_steps.output` 中有 `assigned_agent`、`agent_role`、`result_preview`。
- `agent_audit_events` 中有 `turn.started`、`plan.created`、`plan.step.completed`、`agent.completed`。

## 3. Query Plan Runs

请求代码：

```python
import httpx

resp = httpx.get(
    "http://127.0.0.1:8000/api/v1/plans/runs",
    params={"session_id": "demo-session-001", "limit": 10},
)
print(resp.json())
```

对应数据库：

```text
agent_plan_runs
agent_plan_steps
```

查看 SQL：

```sql
select * from agent_plan_runs where session_id = 'demo-session-001';
select s.* from agent_plan_steps s join agent_plan_runs p on p.plan_id = s.plan_id where p.session_id = 'demo-session-001';
```

## 4. Query One Plan Run

请求代码：

```python
import httpx

plan_id = "把 /api/v1/plans/runs 返回的 plan_id 放这里"
resp = httpx.get(f"http://127.0.0.1:8000/api/v1/plans/runs/{plan_id}")
print(resp.json())
```

对应数据库：

```text
agent_plan_runs.plan_id
agent_plan_steps.plan_id
```

## 5. Query Audit Events

请求代码：

```python
import httpx

resp = httpx.get(
    "http://127.0.0.1:8000/api/v1/audit/events",
    params={"session_id": "demo-session-001", "limit": 50},
)
print(resp.json())
```

对应数据库：

```text
agent_audit_events
```

查看 SQL：

```sql
select event_type, turn_id, payload, created_at
from agent_audit_events
where session_id = 'demo-session-001'
order by id desc;
```

## 6. Document Ingest

请求代码：

```python
import httpx

payload = {
    "title": "经理级差旅政策测试文档",
    "content": "经理级员工国内出差可优先选择高铁二等座或经济舱。超过3000元预算需要提前审批，酒店应符合当地差标。",
    "doc_type": "policy",
    "metadata": {"source": "manual-test"},
}

resp = httpx.post("http://127.0.0.1:8000/api/v1/documents/ingest", json=payload, timeout=90)
print(resp.json())
```

数据位置：

- 如果 Milvus 可用：写入 Milvus collection。
- 如果 Milvus 不可用：写入当前服务进程内的 memory vector store。

注意：

- 文档向量当前不写入 SQLite。
- 你可以通过 `/api/v1/documents/search` 验证它是否可检索。

## 7. Document Search

请求代码：

```python
import httpx

resp = httpx.get(
    "http://127.0.0.1:8000/api/v1/documents/search",
    params={"q": "经理出差预算审批酒店差标", "top_k": 3},
    timeout=90,
)
print(resp.json())
```

数据位置：

```text
Milvus collection 或当前服务进程 memory vector store
```

返回里的 `backend` 会显示使用的是 `milvus` 还是 `memory`。

## 8. Create Scheduler Job

请求代码：

```python
import httpx
from datetime import datetime, timedelta

session_id = "scheduler-session-001"
payload = {
    "session_id": session_id,
    "user_id": "demo-user",
    "prompt": "提醒我检查北京到上海出差审批是否完成。",
    "run_at": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
    "metadata": {"source": "manual-test"},
}

resp = httpx.post("http://127.0.0.1:8000/api/v1/scheduler/jobs", json=payload)
print(resp.json())
```

对应数据库：

```text
agent_scheduled_jobs
```

查看 SQL：

```sql
select * from agent_scheduled_jobs where session_id = 'scheduler-session-001';
```

## 9. List Scheduler Jobs

请求代码：

```python
import httpx

resp = httpx.get(
    "http://127.0.0.1:8000/api/v1/scheduler/jobs",
    params={"session_id": "scheduler-session-001"},
)
print(resp.json())
```

对应数据库：

```text
agent_scheduled_jobs
```

## 10. Run Due Scheduler Jobs

请求代码：

```python
import httpx
from datetime import datetime, timedelta

session_id = "scheduler-due-session-001"

# 先创建一个已经到期的任务
httpx.post(
    "http://127.0.0.1:8000/api/v1/scheduler/jobs",
    json={
        "session_id": session_id,
        "user_id": "demo-user",
        "prompt": "提醒我检查审批状态。",
        "run_at": (datetime.utcnow() - timedelta(seconds=1)).isoformat(),
    },
)

# 再执行到期任务
resp = httpx.post("http://127.0.0.1:8000/api/v1/scheduler/run-due", timeout=90)
print(resp.json())
```

对应数据库：

```text
agent_scheduled_jobs
chat_history
agent_audit_events
agent_plan_runs / agent_plan_steps（如果任务内容触发计划）
```

查看 SQL：

```sql
select * from agent_scheduled_jobs where session_id = 'scheduler-due-session-001';
select * from chat_history where session_id = 'scheduler-due-session-001';
select * from agent_audit_events where session_id = 'scheduler-due-session-001';
```

## 查看 SQLite 的方式

PowerShell 中可以用 Python 查看：

```powershell
D:\miniconda\envs\stbp\python.exe - <<'PY'
import sqlite3
conn = sqlite3.connect("travel_agent.db")
conn.row_factory = sqlite3.Row
for row in conn.execute("select id, session_id, role, substr(content,1,80) as content from chat_history order by id desc limit 10"):
    print(dict(row))
PY
```

或者用 SQLite GUI：

- DB Browser for SQLite
- DBeaver
- DataGrip

打开文件：

```text
D:\java\travel-agent-guide-main\project-python\travel_agent.db
```

## 表和功能对应关系

| 功能 | 表 / 存储 |
| --- | --- |
| 对话消息 | `chat_history` |
| 长期记忆 | `agent_memories` |
| 审计事件 | `agent_audit_events` |
| 定时任务 | `agent_scheduled_jobs` |
| 计划图 | `agent_plan_runs` |
| 计划步骤 | `agent_plan_steps` |
| 文档向量 | Milvus 或内存向量库 |
