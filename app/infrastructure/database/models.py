from datetime import datetime
from sqlalchemy import Column, Float, Integer, String, Text, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), index=True, nullable=True)
    user_id = Column(String(128), index=True, nullable=True)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentMemoryRecord(Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        UniqueConstraint("agent_id", "session_id", "user_id", "text", name="uq_agent_memory_text"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(128), index=True, nullable=False)
    session_id = Column(String(128), index=True, nullable=False)
    user_id = Column(String(128), index=True, nullable=True)
    text = Column(Text, nullable=False)
    source = Column(String(64), nullable=False, default="heuristic")
    importance = Column(Float, nullable=False, default=0.6)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentAuditEventRecord(Base):
    __tablename__ = "agent_audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(128), unique=True, index=True, nullable=False)
    turn_id = Column(String(128), index=True, nullable=False)
    agent_id = Column(String(128), index=True, nullable=False)
    session_id = Column(String(128), index=True, nullable=True)
    user_id = Column(String(128), index=True, nullable=True)
    event_type = Column(String(64), index=True, nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentScheduledJobRecord(Base):
    __tablename__ = "agent_scheduled_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), unique=True, index=True, nullable=False)
    agent_id = Column(String(128), index=True, nullable=False)
    session_id = Column(String(128), index=True, nullable=True)
    user_id = Column(String(128), index=True, nullable=True)
    job_type = Column(String(64), index=True, nullable=False, default="agent_turn")
    prompt = Column(Text, nullable=False)
    run_at = Column(DateTime, index=True, nullable=False)
    status = Column(String(32), index=True, nullable=False, default="pending")
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentPlanRunRecord(Base):
    __tablename__ = "agent_plan_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(String(128), unique=True, index=True, nullable=False)
    turn_id = Column(String(128), index=True, nullable=False)
    agent_id = Column(String(128), index=True, nullable=False)
    session_id = Column(String(128), index=True, nullable=True)
    user_id = Column(String(128), index=True, nullable=True)
    goal = Column(Text, nullable=False)
    status = Column(String(32), index=True, nullable=False, default="planned")
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentPlanStepRecord(Base):
    __tablename__ = "agent_plan_steps"
    __table_args__ = (
        UniqueConstraint("plan_id", "step_index", name="uq_agent_plan_step_index"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    step_id = Column(String(128), unique=True, index=True, nullable=False)
    plan_id = Column(String(128), index=True, nullable=False)
    step_index = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    suggested_tool = Column(String(128), nullable=True)
    status = Column(String(32), index=True, nullable=False, default="planned")
    output = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
