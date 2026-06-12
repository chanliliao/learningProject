import pytest
from sqlmodel import SQLModel


@pytest.mark.asyncio
async def test_async_session_works(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite://")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.db import get_engine, get_session
    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    agen = get_session()
    session = await agen.__anext__()
    assert session is not None
    await agen.aclose()
