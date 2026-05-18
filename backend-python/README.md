# 商旅 Agent Guide（Python）

企业级差旅 AI Agent 服务，基于 FastAPI 提供对话、行程规划、差标校验、会话记忆、知识库检索、运行审计、定时任务执行、计划图追踪和多角色子 Agent 协作。项目正在按 OpenClaw 风格改造成分层 Agent Runtime：Gateway、Runtime、Memory、Tool Registry、Workspace/Skills、Audit、Scheduler、Planning、Multi-Agent Team 逐步拆分。

## 功能概览

- 对话接口：`POST /api/v1/chat`，兼容 OpenAI Chat Completions 风格响应，支持 SSE 流式输出。
- Agent Runtime：`ApiGateway -> AgentRuntime -> AgentSessionManager -> TravelOrchestrator`。
- 组合式记忆：短期窗口、摘要记忆、语义偏好记忆、检索注入；长期语义记忆会持久化到数据库。
- Tool Registry：OpenAI function calling 兼容工具注册、schema 暴露和统一执行。
- Workspace / Skills：从 `workspace/agents/...` 和 `workspace/skills/...` 加载 agent 配置、system prompt 和 skill prompt。
- 运行审计：每轮记录 workspace、skill、tool、memory、model call、tool call 和错误事件。
- Scheduler/Event Driven：支持创建延迟 Agent 任务，到期后后台调用完整 Runtime 执行，并写回任务结果。
- Task/Plan 执行图：复杂差旅请求会生成 plan run 和 plan steps，持久化后执行可确定的工具步骤，并注入 Runtime 上下文。
- Multi-Agent Team：从 `subagents.yaml` 加载 planner、policy checker、itinerary builder、expense reviewer 等子 Agent 角色，并按工具权限执行计划步骤。
- 文档入库与检索：`POST /api/v1/documents/ingest` 和 `GET /api/v1/documents/search`。
- 本地降级：Milvus 不可用时默认启用内存向量库；Embedding 调用失败时默认启用确定性本地向量。

## 项目结构

```text
app/
  main.py                         FastAPI 应用入口与生命周期
  config.py                       环境变量配置
  api/routes/                     HTTP 路由：chat、health、documents、audit、scheduler
  gateway/                        API Channel Gateway
  agent_runtime/                  Agent 生命周期、session、turn、event、config、audit
  agent/orchestrator.py           差旅 Agent 编排器
  core/memory/                    组合式 Agent 记忆与持久化存储
  multi_agent/                    子 Agent 角色、权限和计划步骤分派
  planning/                       计划生成、步骤执行、计划持久化和查询模型
  scheduler/                      定时任务模型与 AgentSchedulerService
  tools/                          主链路 Tool Registry 与内置差旅工具
  workspace/                      Workspace/Skill 加载器
  domain/travel/                  行程、差标、领域模型
  services/                       LLM、Embedding、Milvus/内存向量库服务
  infrastructure/                 数据库、缓存、LLM、观测和向量基础设施
tests/                            单元测试与 API 流程测试
workspace/
  agents/travel-agent/
    agent.yaml                    Agent 配置：模型、工具、技能
    SYSTEM.md                     Agent system prompt
    TOOLS.md                      工具说明
    subagents.yaml                子 Agent 角色与工具权限
  skills/
    travel-policy/
      skill.yaml
      SKILL.md
    expense-control/
      skill.yaml
      SKILL.md
```

## Agent Runtime

```text
HTTP /api/v1/chat
  -> ApiGateway
  -> MessageEnvelope
  -> AgentRuntime.run_turn / stream_turn
  -> AgentSessionManager 加载会话历史
  -> PersistentAgentMemoryStore 加载长期语义记忆
  -> HeuristicTravelPlanner 为复杂请求生成 plan steps
  -> MultiAgentTeam 为 step 分派子 Agent 角色
  -> PlanStepExecutor 执行信息足够且角色有权限的工具步骤
  -> TravelOrchestrator 调用 memory / LLM / tools
  -> AgentSessionManager 保存用户消息和助手回复
  -> PersistentAgentMemoryStore 保存新语义记忆
  -> PersistentAuditStore 写入 agent_audit_events
```

## Workspace / Skills

启动时会读取：

- `WORKSPACE_DIR`：默认 `workspace`
- `DEFAULT_AGENT_ID`：默认 `travel-agent`

加载流程：

```text
WorkspaceLoader
  -> workspace/agents/{agent_id}/agent.yaml
  -> SYSTEM.md
  -> enabled skills
  -> SKILL.md prompt fragments
  -> compose system prompt
  -> filter enabled tools
  -> AgentRuntime
```

当前默认 Agent 启用：

- tools: `plan_travel_itinerary`, `check_travel_policy`
- skills: `travel-policy`, `expense-control`

## Memory

当前记忆分为三层：

- 短期窗口：保留最近对话轮次，用于连续对话。
- 摘要记忆：长对话超过阈值后，把较早轮次压缩为摘要。
- 长期语义记忆：从用户输入中抽取偏好、身份、预算、常驻地等事实，写入 `agent_memories` 表。

每轮执行时：

```text
AgentRuntime
  -> PersistentAgentMemoryStore.load()
  -> TravelOrchestrator.hydrate_semantic_memories()
  -> AgentMemoryManager recall
  -> LLM/tool loop
  -> PersistentAgentMemoryStore.save()
```

服务重启后，已保存的用户偏好仍可被 recall。

## Audit

每轮 Agent turn 会把关键事件写入 `agent_audit_events` 表。当前事件包括：

- `turn.started`
- `memory.loaded`
- `message.persisted`
- `model.call`
- `model.error`
- `tool.called`
- `tool.result`
- `plan.created`
- `plan.step.created`
- `plan.step.started`
- `plan.step.completed`
- `plan.step.skipped`
- `plan.step.failed`
- `plan.completed`
- `memory.persisted`
- `agent.completed`
- `agent.stream.completed`
- `turn.failed`

查询接口：

```text
GET /api/v1/audit/events?session_id=xxx
GET /api/v1/audit/events?turn_id=xxx
GET /api/v1/audit/events?agent_id=travel-agent
```

## Scheduler / Event Driven

Scheduler 用 `agent_scheduled_jobs` 表保存待执行任务。任务到期后会作为 `channel="scheduler"` 的 Agent turn 进入完整 Runtime，因此仍会经过会话、记忆、工具和审计链路。

执行流程：

```text
POST /api/v1/scheduler/jobs
  -> AgentSchedulerService.create_job()
  -> agent_scheduled_jobs(status=pending)
  -> background poll_loop / POST /scheduler/run-due
  -> AgentRuntime.run_turn(channel=scheduler)
  -> agent_scheduled_jobs(status=completed, result={turn_id, assistant_content})
```

接口：

```text
POST /api/v1/scheduler/jobs
GET  /api/v1/scheduler/jobs?status=pending
POST /api/v1/scheduler/run-due
```

`run_at` 支持 ISO datetime。带时区的时间会转换为 UTC 后保存；无时区时间按服务本地传入值保存。

## Task / Plan Graph

复杂差旅请求会在进入 LLM 前由 `HeuristicTravelPlanner` 生成一条 plan run 和多条 plan steps。`MultiAgentTeam` 会为每个 step 分派子 Agent，`PlanStepExecutor` 会在信息足够且角色有工具权限时执行绑定工具，并把 step 状态、工具参数、子 Agent 元数据和结果摘要写回数据库。第一版 planner/executor 是确定性规则实现，优先保证稳定可测；后续可以替换成 LLM planner 或真正并行的多 agent planner。

当前 plan step 会覆盖这些阶段：

- 澄清差旅约束：识别目的地、日期、职级、预算、偏好和审批边界。
- 校验差旅政策：信息足够时调用 `check_travel_policy`，缺日期/城市/预算时标记为 `skipped`。
- 生成候选行程：信息足够时调用 `plan_travel_itinerary`，缺日期/城市时标记为 `skipped`。
- 汇总可执行下一步：输出推荐方案、风险提示和待补充信息。

执行流程：

```text
AgentRuntime
  -> HeuristicTravelPlanner.should_plan()
  -> PersistentPlanStore.save_plan()
  -> MultiAgentTeam.assign_step()
  -> PlanStepExecutor.execute()
  -> PersistentPlanStore.save_execution_result()
  -> AgentEvent(plan.created / plan.step.created)
  -> AgentEvent(plan.step.completed / plan.step.skipped / plan.completed)
  -> inject [Agent plan] system message
  -> inject [Plan execution] system message
  -> TravelOrchestrator
```

查询接口：

```text
GET /api/v1/plans/runs?session_id=xxx
GET /api/v1/plans/runs/{plan_id}
```

## Multi-Agent Team

子 Agent 配置位于：

```text
workspace/agents/travel-agent/subagents.yaml
```

默认角色：

- `travel_planner`：澄清约束、协调专家输出、生成最终行动建议。
- `policy_checker`：只允许使用 `check_travel_policy`。
- `itinerary_builder`：只允许使用 `plan_travel_itinerary`。
- `expense_reviewer`：聚焦预算、报销风险和费用材料。

每个 plan step 的 `output` 会包含：

```json
{
  "assigned_agent": "policy-checker",
  "agent_role": "policy_checker",
  "agent_name": "Policy Checker",
  "allowed_tools": ["check_travel_policy"]
}
```

## 环境要求

- Python 3.11+
- 推荐使用项目现有环境：`conda activate stbp`
- 可选依赖服务：Redis、Milvus 2.x
- 默认数据库：SQLite `travel_agent.db`
- OpenAI 兼容模型网关：通过 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` 配置

## 安装与运行

```bash
conda activate stbp
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问：

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Health: http://127.0.0.1:8000/api/v1/health

## API 摘要

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 服务名与文档入口 |
| GET | `/api/v1/health` | 依赖健康状态 |
| POST | `/api/v1/chat` | 差旅对话，支持 `stream: true` |
| POST | `/api/v1/documents/ingest` | 文档入库 |
| GET | `/api/v1/documents/search` | 文档向量检索 |
| GET | `/api/v1/audit/events` | Agent turn 审计事件查询 |
| GET | `/api/v1/plans/runs` | 查询 Agent 计划图 |
| GET | `/api/v1/plans/runs/{plan_id}` | 查询单个计划图及步骤 |
| POST | `/api/v1/scheduler/jobs` | 创建延迟 Agent 任务 |
| GET | `/api/v1/scheduler/jobs` | 查询调度任务 |
| POST | `/api/v1/scheduler/run-due` | 立即扫描并执行到期任务 |

## 关键配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 空 | OpenAI 兼容接口密钥 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 模型接口地址 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 聊天模型 |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | 向量模型 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./travel_agent.db` | 会话、记忆、审计、调度、计划数据库 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 地址 |
| `MILVUS_HOST` / `MILVUS_PORT` | `localhost` / `19530` | Milvus 地址 |
| `WORKSPACE_DIR` | `workspace` | Agent workspace 根目录 |
| `DEFAULT_AGENT_ID` | `travel-agent` | 默认加载的 Agent |
| `ENABLE_MEMORY_VECTOR_STORE` | `true` | Milvus 不可用时启用内存向量库 |
| `ENABLE_LOCAL_EMBEDDINGS_FALLBACK` | `true` | Embedding 失败时启用本地向量 |

## 测试

```bash
conda activate stbp
python -m pytest -q
```

当前测试覆盖意图识别、RAG 检索合并、Agent memory、持久化 memory、Gateway、AgentRuntime、Tool Registry、Workspace/Skill 加载、Audit 事件持久化、Scheduler 到期任务执行、Plan Graph 生成/持久化、Plan Step Executor 工具执行和 Multi-Agent Team 角色分派。

## 下一阶段

下一步可以继续做端到端真实模型联调和生产化收尾：补充数据库迁移策略、配置样例、错误告警、真实 API smoke case，并根据实际模型返回调优 prompt。

## MySQL persistence

The relational business data backend now defaults to MySQL. It stores chat history, semantic memories, audit events, scheduled jobs, plan runs, and plan steps.

Default local settings:

```text
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=travelagent
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_CHARSET=utf8mb4
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

Initialize the database schema before running the backend or tests:

```powershell
mysql -h localhost -uroot -p123456 < deploy/mysql/schema.sql
```

`DATABASE_URL` remains available as an explicit SQLAlchemy URL override, but normal local and CI runs should use the MySQL settings above.

`agent_memories.text` stores the extracted memory sentence shown back to the agent as long-term context. `agent_memories.text_hash` is a SHA-256 hash used for safe MySQL de-duplication of long memory text.
