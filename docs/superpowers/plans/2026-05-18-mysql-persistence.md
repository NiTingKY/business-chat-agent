# MySQL Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MySQL the default and tested relational persistence backend for chat history, semantic memories, audit events, scheduled jobs, and plan records.

**Architecture:** Runtime settings will resolve MySQL connection details from `MYSQL_*` environment variables unless `DATABASE_URL` explicitly overrides them. SQLAlchemy models remain the application-facing schema, while `deploy/mysql/schema.sql` provides deterministic MySQL initialization for local use and CI. Tests that exercise persistence will run against a real MySQL database URL supplied by `TEST_DATABASE_URL` or the default local MySQL settings.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, aiomysql, MySQL 8, pytest, GitHub Actions service containers.

---

### Task 1: MySQL Defaults and URL Resolution

**Files:**
- Modify: `backend-python/app/config.py`
- Test: `backend-python/tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create tests that instantiate settings with environment overrides and assert:
- MySQL is the default when no `DATABASE_URL` is supplied.
- Explicit `DATABASE_URL` still wins.
- Redis split settings build `redis://host:port/db`.

- [ ] **Step 2: Implement settings properties**

Add `mysql_host`, `mysql_port`, `mysql_database`, `mysql_user`, `mysql_password`, `mysql_charset`, `redis_host`, `redis_port`, `redis_db`, and `redis_password`. Add `resolved_database_url` and `resolved_redis_url` properties.

- [ ] **Step 3: Use resolved URLs at runtime**

Update `app/main.py` to pass `settings.resolved_database_url` and `settings.resolved_redis_url`.

### Task 2: MySQL Schema and Models

**Files:**
- Create: `backend-python/deploy/mysql/schema.sql`
- Modify: `backend-python/app/infrastructure/database/models.py`
- Modify: `backend-python/app/infrastructure/database/repository.py`
- Test: `backend-python/tests/test_persistent_memory.py`

- [ ] **Step 1: Write failing text hash memory test**

Assert two identical semantic memories update a single row by hash, while different texts create separate rows.

- [ ] **Step 2: Add MySQL schema**

Create `chat_history`, `agent_memories`, `agent_audit_events`, `agent_scheduled_jobs`, `agent_plan_runs`, and `agent_plan_steps` with `utf8mb4`, `bigint` primary keys, JSON payload fields, useful indexes, and `agent_memories.text_hash`.

- [ ] **Step 3: Sync SQLAlchemy models**

Use `BigInteger`, MySQL-compatible long text variants, JSON fields, `DateTime(6)` where supported, and `text_hash` uniqueness for semantic memories.

- [ ] **Step 4: Update repository**

Compute SHA-256 hash for memory text before upsert and query by hash.

### Task 3: Test Suite Uses Real MySQL for Persistence

**Files:**
- Create: `backend-python/tests/conftest.py`
- Modify: persistence tests that currently create SQLite temporary files.

- [ ] **Step 1: Create MySQL engine fixture**

Use `TEST_DATABASE_URL` when set, otherwise use settings' resolved MySQL URL. Before each persistence test, create all tables and truncate all known tables in dependency-safe order.

- [ ] **Step 2: Migrate SQLite-dependent tests**

Replace `sqlite+aiosqlite:///{tmp_path}` engine creation with the MySQL fixture for persistent memory, audit, scheduler, planning, and API health tests.

- [ ] **Step 3: Keep non-relational vector fallback tests local**

Milvus Lite and vector fallback tests may still use temporary vector files because they are not the relational business database.

### Task 4: CI and Local Docs

**Files:**
- Modify: `.github/workflows/backend-smoke.yml`
- Modify: `backend-python/.env.example`
- Modify: `backend-python/docker-compose.yml`
- Modify: `backend-python/README.md`

- [ ] **Step 1: Add MySQL service to GitHub Actions**

Start MySQL 8 with `travelagent_test`, wait for health, run `deploy/mysql/schema.sql`, and run pytest with `TEST_DATABASE_URL=mysql+aiomysql://root:123456@127.0.0.1:3306/travelagent_test?charset=utf8mb4`.

- [ ] **Step 2: Update local config examples**

Document `MYSQL_*`, `REDIS_*`, and optional `DATABASE_URL` override.

### Task 5: Verification

**Files:** none

- [ ] **Step 1: Run focused persistence tests**

Run `python -m pytest tests/test_persistent_memory.py tests/test_audit.py tests/test_scheduler.py tests/test_planning.py -q` with MySQL available.

- [ ] **Step 2: Run full backend tests**

Run `python -m pytest -q` from `backend-python`.

- [ ] **Step 3: Run frontend tests**

Run `npm.cmd test` from `frontend-web`.
