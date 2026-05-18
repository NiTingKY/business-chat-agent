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
    database_url: str = ""
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "travelagent"
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_charset: str = "utf8mb4"
    redis_url: str = ""
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
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

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset={self.mysql_charset}"
        )

    @property
    def resolved_redis_url(self) -> str:
        if self.redis_url:
            return self.redis_url
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
