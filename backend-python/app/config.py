from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "商旅-agent-guide"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 768
    openai_max_tokens: int = 2048
    openai_disable_thinking: bool = True
    database_url: str = "sqlite+aiosqlite:///./travel_agent.db"
    redis_url: str = "redis://localhost:6379/0"
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_lite_path: str = ""
    log_level: str = "INFO"
    workspace_dir: str = "workspace"
    default_agent_id: str = "travel-agent"
    enable_memory_vector_store: bool = True
    enable_local_embeddings_fallback: bool = True

    # Agent config
    max_react_iterations: int = 10
    memory_window_size: int = 20
    memory_summary_threshold: int = 15

    # Circuit breaker config
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 30
    circuit_breaker_half_open_max_calls: int = 3


settings = Settings()
