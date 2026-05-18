from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.agent.orchestrator import TravelOrchestrator
from app.agent_runtime.audit import PersistentAuditStore
from app.agent_runtime.agent_config import default_travel_agent_config
from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.session import AgentSessionManager
from app.api.routes import audit as audit_routes
from app.api.routes import chat as chat_routes
from app.api.routes import documents as documents_routes
from app.api.routes import health as health_routes
from app.api.routes import plans as plans_routes
from app.api.routes import scheduler as scheduler_routes
from app.config import settings
from app.core.memory.persistent_store import PersistentAgentMemoryStore
from app.core.logging import configure_logging, get_logger
from app.gateway.api import ApiGateway
from app.multi_agent import MultiAgentTeam
from app.planning import HeuristicTravelPlanner, PersistentPlanStore, PlanStepExecutor
from app.scheduler import AgentSchedulerService
from app.services.milvus_store import get_milvus_store
from app.tools.travel import default_travel_tool_registry, set_policy_document_store
from app.workspace.loader import WorkspaceLoader

logger = get_logger(__name__)


def _setup_tracing() -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": settings.app_name}))
    trace.set_tracer_provider(provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    _setup_tracing()
    trace.get_tracer(__name__)

    app.state.workspace = WorkspaceLoader(settings.workspace_dir).load_agent(
        settings.default_agent_id,
        fallback_model=settings.openai_model,
    )
    app.state.agent_config = app.state.workspace.config
    app.state.multi_agent_team = MultiAgentTeam.from_yaml(
        app.state.workspace.path / "subagents.yaml"
        if app.state.workspace.path
        else Path("__missing_subagents__.yaml")
    )
    all_tools = default_travel_tool_registry()
    app.state.tool_registry = all_tools.filtered(app.state.agent_config.enabled_tools)
    app.state.orchestrator = TravelOrchestrator(
        tool_registry=app.state.tool_registry,
        system_prompt=app.state.agent_config.system_prompt,
    )

    app.state.redis = None
    app.state.redis_error = None
    try:
        app.state.redis = redis.from_url(settings.resolved_redis_url, decode_responses=True)
        await app.state.redis.ping()
        logger.info("redis.connected")
    except Exception as exc:
        logger.warning("redis.unavailable", error=str(exc))
        app.state.redis = None
        app.state.redis_error = str(exc)

    app.state.db_engine: Optional[AsyncEngine] = None
    app.state.db_error = None
    try:
        from app.infrastructure.database.session import create_async_db_engine
        from app.infrastructure.database.models import Base
        app.state.db_engine = create_async_db_engine(
            settings.resolved_database_url,
            pool_size=5,
            max_overflow=10,
        )
        async with app.state.db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database.engine_created")
    except Exception as exc:
        logger.warning("database.engine_failed", error=str(exc))
        if app.state.db_engine is not None:
            await app.state.db_engine.dispose()
        app.state.db_engine = None
        app.state.db_error = str(exc)

    store = get_milvus_store()
    store.connect()
    app.state.milvus = store
    set_policy_document_store(store)
    if store.connected:
        logger.info("milvus.connected")
    else:
        logger.warning("milvus.unavailable")

    app.state.agent_runtime = AgentRuntime(
        agent_id=app.state.agent_config.agent_id,
        orchestrator=app.state.orchestrator,
        sessions=AgentSessionManager(app.state.db_engine),
        config=app.state.agent_config,
        memory_store=PersistentAgentMemoryStore(app.state.db_engine),
        audit_store=PersistentAuditStore(app.state.db_engine),
        plan_store=PersistentPlanStore(app.state.db_engine),
        planner=HeuristicTravelPlanner(),
        plan_executor=PlanStepExecutor(app.state.tool_registry, team=app.state.multi_agent_team),
    )
    app.state.audit_store = PersistentAuditStore(app.state.db_engine)
    app.state.plan_store = PersistentPlanStore(app.state.db_engine)
    app.state.gateway = ApiGateway(app.state.agent_runtime)
    app.state.scheduler_service = AgentSchedulerService(app.state.db_engine)
    app.state.scheduler_task = None
    if app.state.db_engine is not None:
        app.state.scheduler_task = asyncio.create_task(
            app.state.scheduler_service.poll_loop(app.state.agent_runtime, interval_seconds=30)
        )

    yield

    scheduler_service = getattr(app.state, "scheduler_service", None)
    if scheduler_service is not None:
        scheduler_service.stop()
    scheduler_task = getattr(app.state, "scheduler_task", None)
    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
    if app.state.redis is not None:
        await app.state.redis.close()
    set_policy_document_store(None)
    eng = getattr(app.state, "db_engine", None)
    if eng is not None:
        await eng.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_routes.router, prefix="/api/v1")
    app.include_router(chat_routes.router, prefix="/api/v1")
    app.include_router(documents_routes.router, prefix="/api/v1")
    app.include_router(audit_routes.router, prefix="/api/v1")
    app.include_router(plans_routes.router, prefix="/api/v1")
    app.include_router(scheduler_routes.router, prefix="/api/v1")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "docs": "/docs"}

    return app


app = create_app()
