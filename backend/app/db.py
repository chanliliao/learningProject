"""
Database engine and session management.

The async engine is a module-level singleton (``lru_cache(maxsize=1)``).  Sessions
are yielded via ``get_session`` for use as FastAPI dependencies.  Tests use SQLite
in-memory via ``DATABASE_URL`` env override and never touch this module's engine
singleton directly.
"""

from functools import lru_cache
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from app.config import get_settings


@lru_cache(maxsize=1)
def get_engine():
    """Return the module-level async SQLAlchemy engine.

    The engine is created once from ``Settings.database_url`` and reused for the
    lifetime of the process.  The ``lru_cache`` ensures only a single engine (and
    its connection pool) is ever created, regardless of how many times this is called.

    Returns:
        An ``AsyncEngine`` instance.
    """
    return create_async_engine(get_settings().database_url)


async def get_session():
    """FastAPI dependency that yields a per-request async SQLModel session.

    Opens a new session from the shared engine, yields it to the request handler,
    then closes it automatically on exit.  Does not commit — handlers are responsible
    for their own ``commit()`` calls.

    Yields:
        An ``AsyncSession`` for the duration of one HTTP request.
    """
    async with AsyncSession(get_engine()) as session:
        yield session


async def ping_db() -> None:
    """Verify the database is reachable by executing a trivial query.

    Used by the ``/api/health/db`` endpoint.  Raises an exception if the database
    is unreachable or the credentials are wrong.

    Raises:
        sqlalchemy.exc.OperationalError: If the database connection cannot be
            established.
    """
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
