create database if not exists travelagent
  default character set utf8mb4
  collate utf8mb4_unicode_ci;

use travelagent;

create table if not exists chat_history (
  id bigint primary key auto_increment,
  session_id varchar(128) not null,
  user_id varchar(128) null,
  role varchar(32) not null,
  content longtext null,
  tool_calls json null,
  created_at datetime(6) not null default current_timestamp(6),
  index idx_chat_session_created (session_id, created_at),
  index idx_chat_user_created (user_id, created_at)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists agent_memories (
  id bigint primary key auto_increment,
  agent_id varchar(128) not null,
  session_id varchar(128) not null,
  user_id varchar(128) null,
  text longtext not null,
  text_hash char(64) not null,
  source varchar(64) not null default 'heuristic',
  importance double not null default 0.6,
  metadata_json json null,
  created_at datetime(6) not null default current_timestamp(6),
  updated_at datetime(6) not null default current_timestamp(6) on update current_timestamp(6),
  unique key uq_agent_memory_hash (agent_id, session_id, user_id, text_hash),
  index idx_memory_lookup (agent_id, session_id, user_id, importance, updated_at)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists agent_audit_events (
  id bigint primary key auto_increment,
  event_id varchar(128) not null unique,
  turn_id varchar(128) not null,
  agent_id varchar(128) not null,
  session_id varchar(128) null,
  user_id varchar(128) null,
  event_type varchar(64) not null,
  payload json null,
  created_at datetime(6) not null default current_timestamp(6),
  index idx_audit_turn (turn_id),
  index idx_audit_session (session_id, id),
  index idx_audit_agent_type (agent_id, event_type, id)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists agent_scheduled_jobs (
  id bigint primary key auto_increment,
  job_id varchar(128) not null unique,
  agent_id varchar(128) not null,
  session_id varchar(128) null,
  user_id varchar(128) null,
  job_type varchar(64) not null default 'agent_turn',
  prompt longtext not null,
  run_at datetime(6) not null,
  status varchar(32) not null default 'pending',
  result json null,
  error longtext null,
  metadata_json json null,
  created_at datetime(6) not null default current_timestamp(6),
  updated_at datetime(6) not null default current_timestamp(6) on update current_timestamp(6),
  index idx_jobs_due (status, run_at),
  index idx_jobs_session (session_id, id)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists agent_plan_runs (
  id bigint primary key auto_increment,
  plan_id varchar(128) not null unique,
  turn_id varchar(128) not null,
  agent_id varchar(128) not null,
  session_id varchar(128) null,
  user_id varchar(128) null,
  goal longtext not null,
  status varchar(32) not null default 'planned',
  metadata_json json null,
  created_at datetime(6) not null default current_timestamp(6),
  updated_at datetime(6) not null default current_timestamp(6) on update current_timestamp(6),
  index idx_plan_session (session_id, id),
  index idx_plan_agent_status (agent_id, status, id)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists agent_plan_steps (
  id bigint primary key auto_increment,
  step_id varchar(128) not null unique,
  plan_id varchar(128) not null,
  step_index int not null,
  title varchar(256) not null,
  description longtext not null,
  suggested_tool varchar(128) null,
  status varchar(32) not null default 'planned',
  output json null,
  error longtext null,
  created_at datetime(6) not null default current_timestamp(6),
  updated_at datetime(6) not null default current_timestamp(6) on update current_timestamp(6),
  unique key uq_agent_plan_step_index (plan_id, step_index),
  index idx_steps_plan (plan_id, step_index)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;
