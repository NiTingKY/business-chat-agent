# Plan Step Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated plan steps executable and traceable by binding suggested tools to deterministic step execution, persisted step status, outputs, and runtime audit events.

**Architecture:** Keep the current planner stable and add a focused executor that can run safe tool-backed steps only when required inputs are present. The Runtime will create a plan, persist it, execute eligible steps, persist updated statuses, then inject the planned/executed summary into the orchestrator context.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest, existing `AgentToolRegistry`, existing `AgentRuntime`.

---

## Completed Project Summary

- Runtime/Gateway: `POST /api/v1/chat` now flows through `ApiGateway -> AgentRuntime -> AgentSessionManager -> TravelOrchestrator`.
- Memory: short-term, summary, semantic preference recall, and persistent `agent_memories` are implemented.
- Tool Registry: OpenAI-compatible tool schemas and unified invocation are implemented for travel itinerary and policy tools.
- Workspace/Skills: `workspace/agents/travel-agent` and `workspace/skills/*` load system prompt and enabled tools/skills.
- Audit: `agent_audit_events` stores turn, memory, model, tool, plan, and error events; `/api/v1/audit/events` exposes them.
- Scheduler: `agent_scheduled_jobs` supports delayed agent turns and `/api/v1/scheduler/*` endpoints.
- Planning: `agent_plan_runs` and `agent_plan_steps` persist generated plans; `/api/v1/plans/runs*` exposes them.

## File Structure

- Modify: `app/infrastructure/database/repository.py`
  - Add methods to update plan run and step statuses/results.
- Modify: `app/planning/models.py`
  - Add execution summary fields if needed without breaking existing API.
- Create: `app/planning/executor.py`
  - Implement deterministic `PlanStepExecutor`.
- Modify: `app/planning/store.py`
  - Add `save_execution_result(plan)` and public serialization of step outputs.
- Modify: `app/agent_runtime/events.py`
  - Add `plan.step.started`, `plan.step.completed`, `plan.step.skipped`, `plan.step.failed`, `plan.completed`.
- Modify: `app/agent_runtime/runtime.py`
  - Execute eligible plan steps after plan creation and before orchestrator call.
- Modify: `app/main.py`
  - Wire executor using `app.state.tool_registry`.
- Test: `tests/test_plan_executor.py`
  - Unit-test tool argument extraction, skip behavior, and execution.
- Modify: `tests/test_planning.py`
  - Verify Runtime persists executed step statuses and audit events.
- Modify: `README.md`
  - Document Plan Step Executor and current limitations.

---

### Task 1: Repository and Store Updates

- [x] **Step 1: Write failing tests for step status persistence**

Add tests that create a plan, mutate step statuses/output, save execution result, and reload it.

- [x] **Step 2: Run targeted tests**

Run: `D:\miniconda\envs\stbp\python.exe -m pytest -q tests\test_plan_executor.py`

Expected: FAIL because `PersistentPlanStore.save_execution_result` does not exist yet.

- [x] **Step 3: Add repository update methods**

Implement status update methods on `AgentPlanRepository`.

- [x] **Step 4: Add store save method**

Implement `PersistentPlanStore.save_execution_result(plan)`.

- [x] **Step 5: Run targeted tests**

Run: `D:\miniconda\envs\stbp\python.exe -m pytest -q tests\test_plan_executor.py`

Expected: PASS for persistence tests.

### Task 2: Plan Step Executor

- [x] **Step 1: Write executor tests**

Cover:
- policy step completes when date/city/grade/budget inputs exist
- itinerary step completes when date/city/grade/purpose inputs exist
- tool step is skipped when required date is missing
- non-tool steps complete with a local note

- [x] **Step 2: Implement `PlanStepExecutor`**

Use deterministic extraction:
- dates: ISO `YYYY-MM-DD`
- grade: `经理/manager -> manager`, `总监/director -> director`, `高管/executive -> executive`, default `staff`
- cities: known city list, first two as origin/destination
- budget: number before `元` or `CNY`, default only for policy if explicit amount exists

Never fabricate dates. If required fields are missing, mark step `skipped`.

- [x] **Step 3: Run executor tests**

Run: `D:\miniconda\envs\stbp\python.exe -m pytest -q tests\test_plan_executor.py`

Expected: PASS.

### Task 3: Runtime Integration

- [x] **Step 1: Add audit event names**

Add plan step execution event names to `AgentEventType`.

- [x] **Step 2: Inject executor into Runtime**

Runtime should:
- create plan
- save plan
- execute eligible steps
- save execution result
- record execution audit events
- inject plan summary including statuses and output previews

- [x] **Step 3: Wire `main.py`**

Pass `PlanStepExecutor(app.state.tool_registry)` into `AgentRuntime`.

- [x] **Step 4: Run runtime/planning tests**

Run: `D:\miniconda\envs\stbp\python.exe -m pytest -q tests\test_planning.py tests\test_plan_executor.py`

Expected: PASS.

### Task 4: Documentation and Verification

- [x] **Step 1: Update README**

Document plan step execution and limitations.

- [x] **Step 2: Run full tests**

Run: `D:\miniconda\envs\stbp\python.exe -m pytest -q`

Expected: all tests pass.

- [x] **Step 3: Run compile check**

Run: `D:\miniconda\envs\stbp\python.exe -m compileall app tests`

Expected: exit code 0.

- [x] **Step 4: Restart local service and check OpenAPI**

Confirm `/api/v1/plans/runs`, `/api/v1/scheduler/jobs`, and `/api/v1/chat` remain available.
