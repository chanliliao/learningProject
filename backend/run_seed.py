import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import SQLModel
import app.models  # noqa: F401
from app.seed import seed_target_schemas
from app.config import get_settings


async def main():
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine) as s:
        await seed_target_schemas(s)
        await s.commit()
    print("Seeded OK")

asyncio.run(main())
