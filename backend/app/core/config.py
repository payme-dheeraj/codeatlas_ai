"""Application configuration via environment variables using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised application settings.

    All values are read from environment variables (or a .env file).
    Defaults are safe for local development only — override in production.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "CodeAtlas AI"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str = Field(default="dev-secret-change-in-production", min_length=32)
    # When True (default) every data endpoint requires a valid JWT or API key.
    # Set AUTH_REQUIRED=false only for local demos / single-user sandboxes.
    auth_required: bool = True
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://frontend:3000,http://backend:8000"
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated ALLOWED_ORIGINS env var into a list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "codeatlas"
    db_user: str = "codeatlas"
    db_password: str = "password"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    @property
    def database_url(self) -> str:
        """Async PostgreSQL DSN."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync PostgreSQL DSN (used by Alembic)."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_max_connections: int = 50

    @property
    def redis_url(self) -> str:
        """Redis connection URL."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── Celery ────────────────────────────────────────────────────────────────
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    celery_task_serializer: str = "json"
    celery_result_expires: int = 3600  # seconds

    def model_post_init(self, __context: object) -> None:
        """Set Celery URLs from Redis URL if not explicitly provided."""
        if not self.celery_broker_url:
            object.__setattr__(self, "celery_broker_url", self.redis_url)
        if not self.celery_result_backend:
            object.__setattr__(self, "celery_result_backend", self.redis_url)

    # ── MinIO / Object Storage ────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_repos: str = "codeatlas-repos"

    # ── Git / Repository ──────────────────────────────────────────────────────
    repo_clone_base_path: str = "/tmp/codeatlas/repos"
    repo_clone_timeout_seconds: int = 300
    repo_max_size_mb: int = 500

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # ── AI / LLM ─────────────────────────────────────────────────────────────
    llm_provider: Literal["ollama", "openai", "anthropic"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    embedding_dimensions: int = 768
    embedding_backend: Literal["local", "openai"] = "local"
    embedding_model_name: str = "BAAI/bge-base-en-v1.5"
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_code: str = "code_chunks"
    qdrant_collection_docs: str = "doc_chunks"

    @property
    def qdrant_url(self) -> str:
        """Qdrant HTTP URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # ── Observability ─────────────────────────────────────────────────────────
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "codeatlas-backend"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_requests_per_minute: int = 60

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key_in_production(cls, v: str, info: object) -> str:
        """Warn if default secret key is used outside development."""
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


settings = get_settings()
