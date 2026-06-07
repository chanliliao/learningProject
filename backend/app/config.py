from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
