from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://bcagent:bcagent@localhost:5432/bcagentic"

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
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Sandbox
    SANDBOX_IMAGE: str = "bc-agent-sandbox:latest"
    SANDBOX_MEMORY_LIMIT: str = "2g"
    WORKSPACE_BASE: str = "/tmp/bc-agent-workspaces"

    # Default model
    DEFAULT_MODEL: str = "claude-sonnet"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
