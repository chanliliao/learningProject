import os
import pytest
from app.config import get_settings


def test_settings_defaults():
    get_settings.cache_clear()
    s = get_settings()
    assert hasattr(s, "database_url")
    assert hasattr(s, "openrouter_api_key")
    assert hasattr(s, "qdrant_url")
    assert s.llm_mode in ("real", "test")
    assert s.embeddings_provider in ("openrouter", "fastembed")
