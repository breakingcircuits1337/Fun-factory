from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://bcagent:bcagent@localhost:5432/bcagentic"

    # LangGraph checkpointer (uses psycopg3 sync DSN, not asyncpg)
    LANGGRAPH_CHECKPOINTER_URL: str = "postgresql://bcagent:bcagent@localhost:5432/bcagentic"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    LITELLM_BASE_URL: str = "http://localhost:4000"
    LITELLM_MASTER_KEY: Optional[str] = None

    # GitHub
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_WEBHOOK_SECRET: Optional[str] = None

    # GitLab
    GITLAB_TOKEN: Optional[str] = None
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_WEBHOOK_SECRET: Optional[str] = None

    # Linear
    LINEAR_API_KEY: Optional[str] = None

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000

    # Vault
    VAULT_ADDR: Optional[str] = None
    VAULT_TOKEN: Optional[str] = None

    # App
    SECRET_KEY: str = "change-me-in-production"
    API_BEARER_TOKEN: str = "change-me-bearer-token"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Sandbox
    SANDBOX_IMAGE: str = "bc-agent-sandbox:latest"
    SANDBOX_MEMORY_LIMIT: str = "2g"
    WORKSPACE_BASE: str = "/tmp/bc-agent-workspaces"
    SANDBOX_BACKEND: str = "docker"        # "docker" | "microvm"
    MICROVM_RUNTIME: str = "docker-sbx"    # Docker Sandboxes runtime name

    # Default model
    DEFAULT_MODEL: str = "claude-sonnet"

    # LiteLLM virtual keys & budgets
    TASK_BUDGET_USD: float = 5.0

    # Plan mode
    PLAN_MODE_ENABLED: bool = True

    # Coder session handoff
    CODER_TOKEN_LIMIT: int = 80000
    CODER_MAX_SESSIONS: int = 5

    # Langfuse observability
    LANGFUSE_HOST: Optional[str] = None
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_ENABLED: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
