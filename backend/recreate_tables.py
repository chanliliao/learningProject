import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
import app.models  # noqa: F401
from app.config import get_settings


async def main():
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    print("Tables recreated OK")

asyncio.run(main())
