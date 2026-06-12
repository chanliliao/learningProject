"""
Application settings loaded from environment variables and the ``.env`` file.

All configuration is centralised here via ``pydantic-settings``.  Call
``get_settings()`` from any module — the result is cached so the ``.env`` file is
parsed only once per process.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / ``.env``.

    Attributes:
        database_url: SQLAlchemy async database URL.  Must use an async driver
            (``+asyncpg`` for PostgreSQL, ``+aiosqlite`` for SQLite).
        openrouter_api_key: API key for OpenRouter.  Empty string disables real LLM
            calls (only safe in ``llm_mode="test"``).
        openrouter_base_url: OpenRouter or compatible OpenAI-format base URL.
        openrouter_model: Model identifier string passed to OpenRouter, e.g.
            ``"openai/gpt-4o-mini"``.
        qdrant_url: URL of the Qdrant vector store instance.
        embeddings_provider: Which embedding backend to use.  ``"openrouter"`` uses
            OpenAI-compatible embeddings; any other value falls back to FastEmbed.
        langfuse_public_key: Langfuse public key for LLM call tracing.  Empty string
            disables Langfuse tracing.
        langfuse_secret_key: Langfuse secret key.
        langfuse_host: Langfuse API host URL.
        llm_mode: ``"real"`` uses the configured OpenRouter model; ``"test"`` injects
            ``TestModel`` (no API calls, deterministic synthetic output).
        confidence_threshold: Minimum confidence score below which a ``FieldMapping``
            is highlighted as a low-confidence warning in the review UI.
        cors_origins: Allowed CORS origins for the FastAPI middleware.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://pipeline:pipeline@localhost:5433/pipeline"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    qdrant_url: str = "http://localhost:6433"
    embeddings_provider: str = "openrouter"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    llm_mode: str = "real"
    confidence_threshold: float = 0.8
    cors_origins: list[str] = ["http://localhost:5174"]


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance.

    Parses ``.env`` on first call; subsequent calls return the cached object.
    Tests that need to override settings should monkeypatch this function or set
    environment variables before import.

    Returns:
        The singleton ``Settings`` instance.
    """
    return Settings()
