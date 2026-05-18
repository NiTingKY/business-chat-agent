# Multi-Agent Role Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable sub-agent roles so plan steps are assigned to planner, policy, itinerary, and expense specialists with scoped tool permissions and traceable execution metadata.

**Architecture:** Keep the single `AgentRuntime` as the process boundary, but introduce a `MultiAgentTeam` used by `PlanStepExecutor`. Each plan step is routed to a role based on suggested tool and task text; the executor validates that the assigned role is allowed to use the tool before invocation and writes role metadata into step output.

**Tech Stack:** FastAPI, Pydantic v2, PyYAML, pytest, existing `PlanStepExecutor`, existing `AgentToolRegistry`.

---

## Tasks

### Task 1: Team Model and Workspace Config

- [x] Create `app/multi_agent/models.py` with `SubAgentSpec` and `StepAssignment`.
- [x] Create `app/multi_agent/team.py` with default roles and optional YAML loading.
- [x] Add `workspace/agents/travel-agent/subagents.yaml`.
- [x] Add tests for default routing and workspace loading.

### Task 2: Executor Integration

- [x] Modify `PlanStepExecutor` to accept `MultiAgentTeam`.
- [x] Route every step before execution.
- [x] Enforce role tool permissions.
- [x] Include `assigned_agent`, `agent_role`, and `agent_prompt` in step outputs.
- [x] Add tests for role assignment, permission failure, and persisted output metadata.

### Task 3: Runtime and API Visibility

- [x] Wire `MultiAgentTeam` in `main.py`.
- [x] Add audit payload fields for assigned sub-agent role.
- [x] Ensure `/api/v1/plans/runs` exposes assigned role through step output.
- [x] Update README.

### Task 4: Full Verification

- [x] Run targeted tests.
- [x] Run full pytest.
- [x] Run compileall.
- [x] Restart local service and verify OpenAPI/health.
